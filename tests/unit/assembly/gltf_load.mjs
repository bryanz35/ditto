// Loads a .glb with three.js's GLTFLoader and prints each mesh's name and userData as JSON.
// Usage: node gltf_load.mjs <file.glb> <path to node_modules/three>
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [glbPath, threeDir] = process.argv.slice(2);
const url = pathToFileURL(join(threeDir, "examples/jsm/loaders/GLTFLoader.js"));
const { GLTFLoader } = await import(url.href);
const buf = readFileSync(glbPath);
const data = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
new GLTFLoader().parse(
  data,
  "",
  (gltf) => {
    const meshes = [];
    gltf.scene.traverse((o) => {
      if (o.isMesh) meshes.push({ name: o.name, userData: o.userData });
    });
    console.log(JSON.stringify(meshes));
  },
  (err) => {
    console.error(err);
    process.exit(1);
  },
);
