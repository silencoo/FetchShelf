// Run with Node 22+: node --experimental-strip-types scripts/check_resume_video.mjs
import assert from 'node:assert/strict';
import { resumeVideo } from '../webui/src/feed/resumeVideo.ts';

const frames = new Map(), timers = new Map();
let id = 0;
globalThis.requestAnimationFrame = fn => { frames.set(++id, fn); return id; };
globalThis.cancelAnimationFrame = key => frames.delete(key);
globalThis.window = {
  setTimeout(fn) { timers.set(++id, fn); return id; },
  clearTimeout(key) { timers.delete(key); },
};
function tick() {
  const pending = [...frames.values()]; frames.clear();
  for (const fn of pending) fn();
}
function finish() {
  for (const fn of [...timers.values()]) fn();
  assert.equal(frames.size, 0);
  assert.equal(timers.size, 0);
}
class Video extends EventTarget {
  paused = true; seeking = false; ended = false; duration = 30;
  currentSrc = 'fixture.mp4'; time = 5; seeks = [];
  get currentTime() { return this.time; }
  set currentTime(value) { this.time = value; this.seeks.push(value); }
  async play() { this.paused = false; }
}

let v = new Video();
await resumeVideo(v); v.time = 5.2; tick();
assert.deepEqual(v.seeks, [], 'normal playback must not seek'); finish();

v = new Video();
v.play = async () => { v.paused = false; v.time = 4.7; };
await resumeVideo(v);
assert.deepEqual(v.seeks, [5], 'restore a backwards jump during play'); finish();

v = new Video();
await resumeVideo(v); v.time = 4.8; tick();
assert.deepEqual(v.seeks, [5], 'restore a delayed media-clock jump'); finish();

for (const event of ['seeking', 'pause', 'emptied']) {
  v = new Video(); await resumeVideo(v);
  v.dispatchEvent(new Event(event)); v.time = 2; tick();
  assert.deepEqual(v.seeks, [], `${event} cancels the guard`); finish();
}
v = new Video(); await resumeVideo(v); v.currentSrc = 'other.mp4'; v.time = 0; tick();
assert.deepEqual(v.seeks, [], 'do not restore a recycled video'); finish();

v = new Video(); v.time = 29.9;
await resumeVideo(v); v.time = 0.1; tick();
assert.deepEqual(v.seeks, [], 'do not interfere with loops'); finish();

v = new Video(); v.play = async () => { throw new Error('blocked'); };
await assert.rejects(resumeVideo(v), /blocked/); finish();
console.log('PASS: normal resume, immediate/delayed rollback, seek/pause/source changes, loop, rejection and cleanup');
