const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '../app/web/index.html'), 'utf8');
const playerCode = html.slice(html.indexOf('const whepSessions ='), html.indexOf('function whepCodec('));
const stopCode = html.slice(html.indexOf('function stopLiveSlot('), html.indexOf('function stopLive()'));
const startCode = html.slice(html.indexOf('async function startLiveSlot('), html.indexOf('function applyLanePreset()'));

test('the complete inline browser program parses', () => {
  const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)];
  assert(scripts.length > 0);
  for (const script of scripts) new vm.Script(script[1]);
});

test('slow plate requests never overlap and release their slot after completion', async () => {
  const source = html.slice(html.indexOf('async function refreshPlates('), html.indexOf('function can(permission)'));
  let resolveRequest;
  let calls = 0;
  const context = vm.createContext({
    liveCameras: [{ id: 1 }], plateRequests: new Set(), alprInstalled: true,
    paneEls: () => ({ status: {} }), whepSessions: [], renderSlotCar() {}, isTechnician: () => false,
    api: () => { calls++; return new Promise((resolve) => { resolveRequest = resolve; }); },
  });
  vm.runInContext(source, context);
  const first = context.refreshPlates(0);
  await context.refreshPlates(0);
  assert.equal(calls, 1);
  resolveRequest({ live: false });
  await first;
  assert.equal(context.plateRequests.size, 0);
  const second = context.refreshPlates(0);
  assert.equal(calls, 2);
  resolveRequest({ live: false });
  await second;
});

test('failed MJPEG retries back off and a live frame resets the delay', () => {
  const source = html.slice(html.indexOf('function startMjpegLive('), html.indexOf('async function reportViewerTransport('));
  const delays = [];
  const image = { dataset: { cameraId: '1' } };
  const context = vm.createContext({
    snapshotTimers: [], liveObjectUrls: [], liveRetryCounts: {},
    paneEls: () => ({ img: image, status: {} }), URL, Date,
    mediaUrl: () => 'http://site/live?token=test', drawLiveOverlay() {},
    clearTimeout() {}, clearInterval() {},
    setTimeout: (callback, delay) => { delays.push(delay); return delays.length; },
  });
  vm.runInContext(source, context);
  context.startMjpegLive(0, 1);
  image.onerror(); image.onerror(); image.onerror();
  assert.deepEqual(delays, [1000, 2000, 4000]);
  image.onload(); image.onerror();
  assert.equal(delays[3], 1000);
});

function harness() {
  const timers = new Map();
  const calls = [];
  const peers = [];
  const watched = [];
  let timerId = 0;
  const video = { style: {}, videoWidth: 0, play: async () => {}, pause() {}, removeAttribute() {} };
  const image = { style: {}, dataset: {}, getAttribute() {}, removeAttribute() {} };
  const elements = { webrtc: video, img: image, status: {}, camera: {} };
  class Peer {
    constructor() { this.iceGatheringState = 'complete'; peers.push(this); }
    addTransceiver() {}
    async createOffer() { return { type: 'offer', sdp: 'offer' }; }
    async setLocalDescription(offer) { this.localDescription = offer; }
    async setRemoteDescription() {}
    close() { this.closed = true; }
    getReceivers() { return []; }
  }
  const context = vm.createContext({
    URL, AbortSignal, AbortController, RTCPeerConnection: Peer,
    MediaStream: class { constructor(tracks) { this.tracks = tracks; } },
    window: { location: { href: 'https://parking.example/', origin: 'https://parking.example' } },
    state: { token: 'test-token' },
    setTimeout: (callback, delay) => { timers.set(++timerId, { callback, delay }); return timerId; },
    clearTimeout: (identifier) => timers.delete(identifier), clearInterval() {},
    fetch: async (url, options) => {
      calls.push({ url: String(url), options });
      return { ok: true, headers: new Map([['Location', '/cameras/1/live/whep/abc']]), text: async () => 'answer' };
    },
    api: async () => ({ provider: 'MEDIAMTX', transport: 'WEBRTC', whep: '/cameras/1/live/whep', state: 'LIVE' }),
    paneEls: () => elements, loadZone() {}, saveSlotId() {}, watchCamera: (identifier) => watched.push(identifier), unwatchCamera() {},
    refreshPlates() {}, reportViewerTransport() {}, startMjpegLive() {},
    snapshotTimers: [null, null], liveFetchBusy: [], liveFrameSeq: [], liveWatchIds: [],
    liveCameras: [], liveLastCars: [], liveObjectUrls: [], liveOverlays: [],
  });
  vm.runInContext(`${playerCode}\n${stopCode}\n${startCode}\nthis.player = { whepStart, whepClose, whepStop, startLiveSlot, stopLiveSlot, whepSessions };`, context);
  return { ...context.player, context, peers, timers, calls, video, elements, watched };
}

test('connected transport is not LIVE until a video frame arrives; audio cannot hide video', async () => {
  const player = harness();
  const states = [];
  const session = await player.whepStart(player.video, '/cameras/1/live/whep', (state) => states.push(state));
  session.pc.connectionState = 'connected';
  session.pc.onconnectionstatechange();
  assert.deepEqual(states, ['connected']);
  session.pc.ontrack({ track: { kind: 'audio' }, streams: [] });
  assert.equal(player.video.srcObject, undefined);
  const track = { kind: 'video' };
  session.pc.ontrack({ track, streams: [] });
  assert.equal(player.video.srcObject.tracks[0], track);
  player.video.videoWidth = 640;
  player.video.onloadeddata();
  assert.equal(states.at(-1), 'video');
  assert.equal(player.timers.size, 0);
  assert.equal(player.calls[0].options.headers.Authorization, 'Bearer test-token');
  player.whepClose(session);
});

test('switching cameras closes the previous peer and deletes the server session', async () => {
  const player = harness();
  await player.startLiveSlot(0, { id: 1 });
  const oldPeer = player.peers[0];
  await player.startLiveSlot(0, { id: 2 });
  assert.equal(oldPeer.closed, true);
  assert.equal(player.peers.length, 2);
  assert(player.calls.some((call) => call.options.method === 'DELETE'));
  player.stopLiveSlot(0);
  assert.equal(player.timers.size, 0);
});

test('temporary signaling failure falls back and schedules a successful WHEP retry', async () => {
  const player = harness();
  const originalFetch = player.context.fetch;
  player.context.fetch = async () => ({ ok: false, status: 503 });
  await player.startLiveSlot(0, { id: 1 });
  assert.equal(player.peers[0].closed, true);
  assert.match(player.elements.status.textContent, /WHEP SIGNALING FAILED/);
  const retry = [...player.timers.values()].find((timer) => timer.delay === 5000);
  assert(retry);
  player.context.fetch = originalFetch;
  retry.callback();
  for (let index = 0; index < 20; index += 1) await Promise.resolve();
  assert.equal(player.peers.length, 2);
  assert(player.whepSessions[0]);
  assert.deepEqual(player.watched, [1]);
  player.stopLiveSlot(0);
});

test('missing video track is visible and cross-origin requests never receive the API token', async () => {
  const player = harness();
  const states = [];
  const session = await player.whepStart(player.video, 'http://lan-server:8889/cam1/whep', (state) => states.push(state));
  assert.equal(player.calls[0].options.headers.Authorization, undefined);
  [...player.timers.values()].find((timer) => timer.delay === 10000).callback();
  assert.equal(states.at(-1), 'no-video-track');
  player.whepClose(session);
  assert.equal(session.pc.closed, true);
});

test('switching during signaling immediately closes and aborts the pending peer', async () => {
  const player = harness();
  let release;
  player.context.fetch = () => new Promise((resolve) => { release = resolve; });
  const opening = player.startLiveSlot(0, { id: 1 });
  for (let index = 0; index < 20; index += 1) await Promise.resolve();
  const pending = player.whepSessions[0];
  assert(pending);
  player.stopLiveSlot(0);
  assert.equal(pending.pc.closed, true);
  assert.equal(pending.abort.signal.aborted, true);
  release({ ok: true, headers: new Map(), text: async () => 'answer' });
  await opening;
  assert.equal(player.whepSessions[0], null);
});

test('a connected peer with stalled decoded-frame counters reports failure', async () => {
  const player = harness();
  let elapsed = 0;
  player.context.performance = { now: () => elapsed };
  player.context.RTCPeerConnection.prototype.getStats = async () => new Map([['video', { type: 'inbound-rtp', kind: 'video', framesDecoded: 0 }]]);
  const states = [];
  const session = await player.whepStart(player.video, '/cameras/1/live/whep', (state) => states.push(state));
  elapsed = 9000;
  await [...player.timers.values()].find((timer) => timer.delay === 2000).callback();
  assert.equal(states.at(-1), 'no-frames');
  player.whepClose(session);
});
