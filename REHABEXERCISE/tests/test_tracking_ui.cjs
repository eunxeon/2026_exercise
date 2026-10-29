const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const path = require("node:path");
const nodes = new Map();
function node(id) {
    if (!nodes.has(id)) nodes.set(id, {textContent: "", hidden: true, addEventListener() {},
        classList: {contains() {return true;}}, getContext() {return {clearRect() {}, strokeRect() {}, fillText() {}};}});
    return nodes.get(id);
}
const context = vm.createContext({URLSearchParams, Intl, console,
    window: {location: {search: ""}}, document: {getElementById: node, querySelectorAll() {return [];}},
    fetch() {throw new Error("Paused/empty sessions must not save");},
    clearInterval() {}, clearTimeout() {}, setTimeout() {}, AbortController});
let source = fs.readFileSync(path.join(__dirname, "../static/js/main.js"), "utf8");
source = source.replace("initializeApp();", "");
vm.runInContext(source, context);
vm.runInContext('selectedExercise = {key: "shoulder", angle: 120}; exerciseSession = {samples: [], saved: false};', context);
node("accuracy-value").textContent = "85%";
node("rep-counter").textContent = "1 / 3";
for (const state of ["WAITING_TARGET", "MULTIPLE_PEOPLE", "TARGET_LOST", "OCCLUDED", "LOW_CONFIDENCE", "TRACKING_ERROR"]) {
    context.result = {analysis_valid: false, state, feedback: "paused", accuracy: 0, max_angle: 180,
        tracking: {requires_confirmation: state === "TARGET_LOST"}};
    vm.runInContext("applyAnalysisResult(result); collectExerciseSample(result);", context);
    assert.equal(node("accuracy-value").textContent, "85%");
    assert.equal(node("rep-counter").textContent, "1 / 3");
    assert.equal(vm.runInContext("exerciseSession.samples.length", context), 0);
}
vm.runInContext('selectedExercise = {key: "rom_shoulder"}; romLatestResult = {max_angle: 93}; applyAnalysisResult(result);', context);
assert.equal(vm.runInContext("romLatestResult.max_angle", context), 93);
(async () => {
    await vm.runInContext("finishExerciseSession()", context);
    assert.match(node("rom-result-message").textContent, /저장할 수 없습니다/);
    console.log("UI pause, ROM preservation, invalid sample exclusion, empty save: OK");
})().catch(error => {console.error(error); process.exitCode = 1;});
