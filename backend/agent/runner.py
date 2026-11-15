"""AgentRunner: the Runner (backend/contracts/runner.py) backed by the deepagents orchestrator.

Model work only: the sub-agents' tools save spec.json and firmware/src/main.cpp after the
StageRunner's checks pass; the engine runs the remaining stages and emits "done".
"""

import asyncio
import base64
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from deepagents.backends.utils import create_file_data
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from backend.agent.orchestrator import (
    AGENTS_MD,
    ModelLike,
    build_agent,
    house_rules,
    model_spec,
    reference_files,
)
from backend.agent.tools import RunContext, make_tools
from backend.contracts.events import Event, Question, Stage, Todo
from backend.contracts.parts import PartLibrary, load_library
from backend.contracts.runner import (
    AnswerRequest,
    EditRequest,
    Emit,
    NoSpec,
    RunRequest,
    StageRunner,
    run_dir_for,
)
from backend.contracts.spec import ProjectSpec
from backend.contracts.tools import ToolBox

NO_ANSWER = "No answer: state your assumption in the spec's assumptions and continue."
LIMIT_REACHED = (
    "Question limit reached: don't ask again. "
    "State your assumption in the spec's assumptions and continue."
)


class AgentRunner:
    def __init__(
        self,
        toolbox: ToolBox,
        model: ModelLike | None,
        run_stages: StageRunner,
        *,
        lib: PartLibrary | None = None,
        models: dict[str, ModelLike] | None = None,
        question_timeout_s: float = 120.0,
        max_questions: int = 2,
    ):
        """model: P2D_MODEL when None. models: per-sub-agent overrides by name.
        max_questions limits clarifying questions per run; BOM approvals don't count."""
        self.toolbox, self.run_stages = toolbox, run_stages
        self.model, self.models = model_spec(model), models or {}
        self.lib = lib or load_library()
        self.question_timeout_s, self.max_questions = question_timeout_s, max_questions
        # shortcut: in-memory threads, so edit() after an API restart starts a fresh thread
        # (it still gets the current spec); use a SQLite checkpointer if that matters.
        self.checkpointer = InMemorySaver()
        self._pending: dict[tuple[str, str], asyncio.Future[str]] = {}
        self._asked: dict[str, int] = {}

    async def run(self, request: RunRequest, emit: Emit) -> ProjectSpec:
        ctx = self._ctx(request.run_id, emit, request.prompt)
        ctx.user = request.user
        _plan(ctx, "running", "Reading the prompt")
        content = await self._content(request, ctx)
        await self._drive(ctx, content)
        return _finish(ctx)

    async def edit(self, run_id: str, request: EditRequest, emit: Emit) -> ProjectSpec:
        spec = self._ctx(run_id, emit, "").load_spec()
        if spec is None:
            raise RuntimeError(f"run {run_id} has no saved spec to edit")
        ctx = self._ctx(run_id, emit, spec.prompt)
        _plan(ctx, "running", f"Editing: {request.instruction}")
        message = (
            f"Edit request: {request.instruction}\n\n"
            f"Current spec (rev {spec.rev}):\n{spec.model_dump_json()}"
        )
        await self._drive(ctx, message)
        return _finish(ctx, after_rev=spec.rev)

    async def answer(self, run_id: str, request: AnswerRequest) -> None:
        future = self._pending.get((run_id, request.question_id))
        if future and not future.done():
            future.set_result(request.answer)

    def _ctx(self, run_id: str, emit: Emit, prompt: str) -> RunContext:
        return RunContext(run_id, emit, self.run_stages, self.lib, prompt)

    async def _content(self, request: RunRequest, ctx: RunContext) -> str | list:
        text = f"{request.prompt}\n\nUser context: {request.user.model_dump_json()}"
        if not request.files:
            return text
        run_dir = run_dir_for(request.run_id)
        result = await asyncio.to_thread(
            self.toolbox.preprocess_input,
            [run_dir / f for f in request.files],
            run_dir / "input",
        )
        if not result.ok:
            ctx.emit(
                _event(
                    ctx,
                    "plan",
                    "running",
                    "Couldn't read the uploads",
                    errors=result.errors,
                )
            )
            return text
        if transcript := result.data.get("transcript"):
            text += f"\n\nVideo transcript:\n{transcript}"
        blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for image in result.data.get("images", []):
            mime = mimetypes.guess_type(image)[0] or "image/png"
            data = base64.b64encode(Path(image).read_bytes()).decode()
            blocks.append({"type": "image", "base64": data, "mime_type": mime})
        return blocks

    async def _drive(self, ctx: RunContext, content: str | list) -> None:
        """Send one user message; stream the agent, forwarding todo updates, and answer its
        questions until it ends."""
        files = {AGENTS_MD: create_file_data(house_rules())} | {
            path: create_file_data(src.read_text())
            for path, src in reference_files().items()
        }
        payload: dict | Command = {
            "messages": [{"role": "user", "content": content}],
            "files": files,
        }
        # Edits have no ctx.user: the saved spec keeps the run's user.
        user = ctx.user or getattr(ctx.load_spec(), "user", None)
        agent = build_agent(
            make_tools(ctx),
            self.model,
            self.checkpointer,
            self.models,
            user,
            ctx.pin_macros,
        )
        # Every event of this turn carries the turn's token count so far (data.tokens), sub-agents included.
        usage = UsageMetadataCallbackHandler()
        emit = ctx.emit
        ctx.emit = lambda e: emit(
            e.model_copy(update={"data": e.data | {"tokens": _tokens(usage)}})
        )
        config = {
            "configurable": {"thread_id": ctx.run_id},
            "recursion_limit": 200,
            "callbacks": [usage],
            # LangSmith (when LANGSMITH_TRACING is set): one trace per message, findable by run id.
            "run_name": "p2d",
            "metadata": {"p2d_run_id": ctx.run_id},  # "run_id" is LangGraph's own key
        }
        todos = (await agent.aget_state(config)).values.get("todos")
        while True:
            async for state in agent.astream(payload, config, stream_mode="values"):
                if state.get("todos") and state["todos"] != todos:
                    todos = state["todos"]
                    items = [Todo.model_validate(t).model_dump() for t in todos]
                    ctx.emit(
                        _event(
                            ctx,
                            "plan",
                            "running",
                            "Plan updated",
                            data={"todos": items},
                        )
                    )
            state = await agent.aget_state(config)
            if not state.interrupts:
                messages = state.values.get("messages") or [None]
                if reply := _text(messages[-1]):
                    ctx.emit(
                        _event(ctx, "plan", "running", reply, data={"chat": "agent"})
                    )
                return
            interrupts = state.interrupts
            resume = {}
            for interrupt in interrupts:
                requests = interrupt.value["action_requests"]
                answers = [await self._ask(ctx, r["args"]) for r in requests]
                resume[interrupt.id] = {
                    "decisions": [{"type": "respond", "message": a} for a in answers]
                }
            payload = Command(resume=resume)

    async def _ask(self, ctx: RunContext, args: dict) -> str:
        """One ask_user call: a "waiting" event, then the answer or, after the timeout, NO_ANSWER."""
        stage: Stage = "bom" if args.get("stage") == "bom" else "plan"
        if stage == "plan":
            asked = self._asked.get(ctx.run_id, 0)
            if asked >= self.max_questions:
                return LIMIT_REACHED
            self._asked[ctx.run_id] = asked + 1
        question = Question(
            id=uuid.uuid4().hex[:12],
            text=args["question"],
            options=args.get("options") or [],
            timeout_s=self.question_timeout_s,
        )
        key = (ctx.run_id, question.id)
        self._pending[key] = asyncio.get_running_loop().create_future()
        ctx.emit(
            _event(
                ctx,
                stage,
                "waiting",
                question.text,
                data={"question": question.model_dump()},
            )
        )
        try:
            answer = await asyncio.wait_for(self._pending[key], self.question_timeout_s)
            ctx.emit(_event(ctx, stage, "running", f"Answer: {answer}"))
            return answer
        except TimeoutError:
            message = f"No answer after {self.question_timeout_s:g} s: continuing with an assumption"
            ctx.emit(_event(ctx, stage, "running", message))
            return NO_ANSWER
        finally:
            del self._pending[key]


def _event(ctx: RunContext, stage: Stage, status, message: str, **kw) -> Event:
    spec = ctx.load_spec()
    return Event(
        run_id=ctx.run_id,
        stage=stage,
        status=status,
        message=message,
        spec_rev=spec.rev if spec else 0,
        **kw,
    )


def _plan(ctx: RunContext, status, message: str) -> None:
    ctx.emit(_event(ctx, "plan", status, message))


def _tokens(usage: UsageMetadataCallbackHandler) -> dict[str, int]:
    """Input and output tokens summed over every model the turn called."""
    totals = usage.usage_metadata.values()
    return {
        "input": sum(u.get("input_tokens", 0) for u in totals),
        "output": sum(u.get("output_tokens", 0) for u in totals),
    }


def _text(message) -> str:
    """The text of the agent's last message: its reply to the user."""
    content = getattr(message, "content", "")
    if isinstance(content, list):
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content.strip()


def _finish(ctx: RunContext, after_rev: int = 0) -> ProjectSpec:
    """The saved spec. after_rev: the rev an edit started from; an edit that saved nothing newer
    (it answered a question, or couldn't make the change) keeps that spec, and its reply says why."""
    spec = ctx.load_spec()
    if spec is None:
        _plan(ctx, "failed", "No validated spec yet")
        raise NoSpec(f"run {ctx.run_id}: the agent ended without a validated spec")
    if spec.rev <= after_rev:
        _plan(ctx, "passed", f"No change to the spec (rev {spec.rev})")
        return spec
    _plan(ctx, "passed", f"Spec rev {spec.rev} saved")
    return spec
