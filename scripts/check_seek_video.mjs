import assert from 'node:assert/strict';
import { seekVideo } from '../webui/src/feed/seekVideo.ts';
class Video extends EventTarget {
  duration=20; currentSrc='fixture.mp4'; seeking=false; time=1; targets=[]; paused=true;
  get currentTime(){return this.time;}
  set currentTime(value){this.targets.push(value);this.time=value;this.seeking=true;}
  complete(){this.seeking=false;this.dispatchEvent(new Event('seeked'));}
}
const v=new Video();
seekVideo(v,3);seekVideo(v,5);seekVideo(v,9);
assert.deepEqual(v.targets,[3]);
v.complete();assert.deepEqual(v.targets,[3,9]);
v.complete();assert.equal(v.paused,true);
seekVideo(v,12);assert.deepEqual(v.targets,[3,9,12]);
v.dispatchEvent(new Event('emptied'));v.currentSrc='other.mp4';v.complete();
assert.deepEqual(v.targets,[3,9,12]);
seekVideo(v,NaN);assert.equal(v.targets.length,3);
console.log('PASS: coalesced drag, final target, pause preserved, source cleanup, invalid target');
