import Daily from "@daily-co/daily-js";

const form = document.querySelector("#connect-form");
const passwordInput = document.querySelector("#password");
const connectButton = document.querySelector("#connect");
const controls = document.querySelector("#call-controls");
const muteButton = document.querySelector("#mute");
const errorBox = document.querySelector("#error");
const audio = document.querySelector("#remote-audio");
const playButton = document.querySelector("#play-audio");
let call = null;
let session = null;
let password = "";
let poll = null;
let busy = false;
let stopping = false;
let connected = false;

fetch("/api/config")
  .then((response) => response.ok ? response.json() : Promise.reject())
  .then((config) => {
    document.querySelector("#provider-name").textContent = `${config.providerName} voice assistant`;
    const routed = config.dataProcessors.includes("OpenRouter") ? " OpenRouter also routes data to its selected model providers." : "";
    document.querySelector("#data-processors").textContent = `Conversation data is processed by ${config.dataProcessors.join(", ")}.${routed}`;
  })
  .catch(() => {}); // The generic privacy text remains accurate if this request fails.

function setStatus(text, state = "idle") {
  document.querySelector("#status").textContent = text;
  document.querySelector("#voice-window").dataset.state = state;
  document.querySelector("#status-dot").classList.toggle("connected", state === "connected");
}

function showError(message = "") {
  errorBox.textContent = message;
  errorBox.hidden = !message;
}

async function api(path, method = "GET", options = {}) {
  const response = await fetch(path, {
    method, headers: { Authorization: `Bearer ${password}` },
    signal: AbortSignal.timeout(path === "/api/start" ? 75000 : 10000), ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "The service is unavailable. Try again shortly.");
  }
  return response.status === 204 ? null : response.json();
}

async function disconnect(message = "Conversation ended") {
  if (stopping) return;
  stopping = true;
  connected = false;
  clearInterval(poll);
  poll = null;
  const endedSession = session;
  const endedCall = call;
  session = null;
  call = null;
  controls.hidden = true;
  playButton.hidden = true;
  try {
    const results = await Promise.allSettled([
      endedCall?.destroy(),
      endedSession ? api(`/api/sessions/${endedSession.id}`, "DELETE") : Promise.resolve(),
    ]);
    if (results.some((result) => result.status === "rejected")) {
      showError("The connection closed, but cleanup could not be confirmed. The session has an automatic time limit.");
    }
  } finally {
    audio.srcObject = null;
    form.hidden = false;
    connectButton.disabled = false;
    passwordInput.disabled = false;
    muteButton.textContent = "Mute microphone";
    muteButton.setAttribute("aria-pressed", "false");
    document.querySelector("#timer").textContent = "Ready when you are";
    setStatus(message);
    busy = false;
    stopping = false;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  busy = true;
  password = passwordInput.value;
  passwordInput.disabled = true;
  connectButton.disabled = true;
  showError();
  setStatus("Checking access…", "connecting");
  try {
    await api("/api/auth", "POST");
    call = Daily.createCallObject({ videoSource: false, audioSource: true, dailyConfig: { avoidEval: true } });
    call.on("track-started", (event) => {
      if (event.track.kind === "audio" && !event.participant?.local) {
        audio.srcObject = new MediaStream([event.track]);
        audio.play().catch(() => { playButton.hidden = false; });
      }
    });
    call.on("error", () => {
      showError("The audio connection failed. Check your network and reconnect.");
      if (connected) void disconnect("Connection lost");
    });
    call.on("left-meeting", () => { if (connected) void disconnect(); });
    setStatus("Allow microphone access to continue", "connecting");
    // Obtain microphone permission before creating billable provider resources.
    await call.startCamera({ videoSource: false });
    const microphone = call.participants().local?.tracks.audio;
    if (!(microphone?.persistentTrack || microphone?.track)) {
      throw new Error("Allow microphone access and make sure a microphone is connected, then try again.");
    }
    setStatus("Getting your assistant ready…", "connecting");
    session = await api("/api/start", "POST");
    await call.join({ url: session.url, token: session.token, startVideoOff: true });
    connected = true;
    form.hidden = true;
    passwordInput.value = "";
    controls.hidden = false;
    setStatus("Connected · speak naturally", "connected");
    async function pollSession() {
      if (!session) return;
      const current = session;
      const seconds = Math.max(0, current.expiresAt - Math.floor(Date.now() / 1000));
      document.querySelector("#timer").textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")} remaining`;
      if (!seconds) { await disconnect("Session time limit reached"); return; }
      try {
        const state = await api(`/api/sessions/${current.id}`);
        if (session === current && state.status === "ended") await disconnect();
      } catch {
        if (session === current) {
          showError("The service connection was lost. Reconnect to try again.");
          await disconnect("Connection lost");
        }
      }
      if (session === current) poll = setTimeout(pollSession, 2000);
    }
    void pollSession();
  } catch (error) {
    const permissionDenied = error?.name === "NotAllowedError" || error?.name === "NotFoundError";
    await disconnect("Not connected");
    showError(permissionDenied ? "Allow microphone access and make sure a microphone is connected, then try again."
      : (typeof error === "string" ? error : error?.message) || "The audio connection could not start. Check your network and reconnect.");
  }
});

muteButton.addEventListener("click", () => {
  if (!call) return;
  const muted = muteButton.getAttribute("aria-pressed") !== "true";
  call.setLocalAudio(!muted);
  muteButton.setAttribute("aria-pressed", String(muted));
  muteButton.textContent = muted ? "Unmute microphone" : "Mute microphone";
  setStatus(muted ? "Microphone muted" : "Connected · speak naturally", "connected");
});

document.querySelector("#disconnect").addEventListener("click", () => { void disconnect(); });
playButton.addEventListener("click", async () => {
  try { await audio.play(); playButton.hidden = true; }
  catch { showError("Your browser blocked playback. Check its audio permissions."); }
});

window.addEventListener("pagehide", () => {
  if (session) {
    void api(`/api/sessions/${session.id}`, "DELETE", { keepalive: true }).catch(() => {});
  }
});
