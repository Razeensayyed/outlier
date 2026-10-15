'use strict';

const csInterface = new CSInterface();
let seqInfo = null;

// ── Init ──────────────────────────────────────────────────────────
window.addEventListener('load', () => {
  loadKeys();
  initSettingsToggle();
  refreshSequence();
});

function initSettingsToggle() {
  const toggle = document.getElementById('settings-toggle');
  const body   = document.getElementById('settings-body');
  body.style.maxHeight = body.scrollHeight + 'px';
  toggle.classList.add('open');
  toggle.addEventListener('click', () => {
    const open = toggle.classList.toggle('open');
    body.classList.toggle('closed', !open);
    if (open) body.style.maxHeight = body.scrollHeight + 'px';
  });
}

function toggleVis(id) {
  const el = document.getElementById(id);
  el.type = el.type === 'password' ? 'text' : 'password';
}

// ── Keys ──────────────────────────────────────────────────────────
function saveKeys() {
  localStorage.setItem('vc_openai',    document.getElementById('openai-key').value.trim());
  localStorage.setItem('vc_anthropic', document.getElementById('anthropic-key').value.trim());
  setStatus('Keys saved', 'success');
  setTimeout(() => setStatus('Ready', 'idle'), 1500);
}

function loadKeys() {
  const ok = localStorage.getItem('vc_openai')    || '';
  const ak = localStorage.getItem('vc_anthropic') || '';
  document.getElementById('openai-key').value    = ok;
  document.getElementById('anthropic-key').value = ak;
}

function getKeys() {
  return {
    openai:    document.getElementById('openai-key').value.trim(),
    anthropic: document.getElementById('anthropic-key').value.trim(),
  };
}

// ── Sequence ──────────────────────────────────────────────────────
function refreshSequence() {
  csInterface.evalScript('getSequenceInfo()', (result) => {
    try {
      const info = JSON.parse(result);
      if (info.error) {
        document.getElementById('seq-name').textContent = info.error;
        document.getElementById('run-btn').disabled = true;
        return;
      }
      seqInfo = info;
      document.getElementById('seq-name').textContent =
        info.name + '  (' + formatTime(info.duration) + ')';
      document.getElementById('run-btn').disabled = false;
      setStatus('Sequence loaded — click to find viral clips', 'idle');
    } catch (e) {
      document.getElementById('seq-name').textContent = 'Error reading sequence';
    }
  });
}

// ── Pipeline ──────────────────────────────────────────────────────
async function runPipeline() {
  const keys = getKeys();
  if (!keys.openai)    return alert('Please enter your OpenAI API key in Settings.');
  if (!keys.anthropic) return alert('Please enter your Anthropic API key in Settings.');
  if (!seqInfo || !seqInfo.filePath) return alert('No video file found in the active sequence.');

  document.getElementById('run-btn').disabled = true;
  document.getElementById('pipeline').style.display = 'flex';
  document.getElementById('progress-wrap').style.display = 'block';
  document.getElementById('results').classList.add('hidden');
  setProgress(0);

  try {
    // Step 1: already have seqInfo from refreshSequence
    stepState('step-read', 'active', 'reading...');
    await delay(400);
    stepState('step-read', 'done', 'done');
    setProgress(20);

    // Step 2: Transcribe
    stepState('step-transcribe', 'active', 'uploading...');
    setStatus('Transcribing audio — this may take 1–3 minutes for long videos…', 'working');
    const transcript = await transcribeVideo(seqInfo.filePath, keys.openai);
    stepState('step-transcribe', 'done', 'done');
    setProgress(60);

    // Step 3: Analyse
    stepState('step-analyse', 'active', 'analysing...');
    setStatus('Claude is finding the best viral moments…', 'working');
    const clipMin = parseInt(document.getElementById('clip-min').value) || 30;
    const clipMax = parseInt(document.getElementById('clip-max').value) || 90;
    const viralClips = await findViralClips(transcript, keys.anthropic, clipMin, clipMax);
    stepState('step-analyse', 'done', 'done');
    setProgress(80);

    // Step 4: Cut
    stepState('step-cut', 'active', 'cutting...');
    setStatus('Creating sequences in Premiere Pro…', 'working');
    await cutClipsInPremiere(viralClips);
    stepState('step-cut', 'done', 'done');
    setProgress(100);

    setStatus('Done! 3 viral clip sequences created in your project.', 'success');
    renderResults(viralClips);

  } catch (err) {
    setStatus('Error: ' + err.message, 'error');
    console.error(err);
  } finally {
    document.getElementById('run-btn').disabled = false;
  }
}

// ── Transcription (Whisper) ───────────────────────────────────────
async function transcribeVideo(filePath, apiKey) {
  // Read file via Node.js (available in CEP Chromium environment)
  const fs     = require('fs');
  const path   = require('path');
  const buffer = fs.readFileSync(filePath);
  const ext    = path.extname(filePath).toLowerCase() || '.mp4';
  const mime   = getMime(ext);

  const blob = new Blob([buffer], { type: mime });
  const formData = new FormData();
  formData.append('file', blob, 'media' + ext);
  formData.append('model', 'whisper-1');
  formData.append('response_format', 'verbose_json');
  formData.append('timestamp_granularities[]', 'segment');

  const res = await fetch('https://api.openai.com/v1/audio/transcriptions', {
    method: 'POST',
    headers: { 'Authorization': 'Bearer ' + apiKey },
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error('Whisper API error: ' + ((err.error && err.error.message) || res.status));
  }

  const data = await res.json();

  // Build timestamped transcript string for Claude
  let text = '';
  if (data.segments && data.segments.length > 0) {
    data.segments.forEach(function(seg) {
      text += '[' + formatTime(seg.start) + ' - ' + formatTime(seg.end) + '] ' + seg.text.trim() + '\n';
    });
  } else {
    text = data.text || '';
  }
  return text;
}

function getMime(ext) {
  const map = {
    '.mp4':  'video/mp4',
    '.mov':  'video/quicktime',
    '.avi':  'video/avi',
    '.mkv':  'video/x-matroska',
    '.mp3':  'audio/mpeg',
    '.m4a':  'audio/mp4',
    '.wav':  'audio/wav',
    '.mxf':  'video/mxf',
    '.mts':  'video/mts',
    '.m2t':  'video/m2t',
    '.webm': 'video/webm',
  };
  return map[ext] || 'video/mp4';
}

// ── Viral analysis (Claude) ───────────────────────────────────────
async function findViralClips(transcript, apiKey, minSec, maxSec) {
  const prompt =
    'You are an expert social media strategist. Analyse this video transcript (with timestamps) ' +
    'and identify the 3 segments that would perform best as short-form viral content on TikTok, ' +
    'Instagram Reels, or YouTube Shorts.\n\n' +
    'Selection criteria (in order of priority):\n' +
    '1. Strong hook in the first 3 seconds that stops the scroll\n' +
    '2. Emotional peak — surprise, laughter, inspiration, controversy\n' +
    '3. A single clear insight, story, or payoff\n' +
    '4. Self-contained — understandable without context\n' +
    '5. Length: each clip must be between ' + minSec + ' and ' + maxSec + ' seconds\n\n' +
    'Transcript:\n' + transcript + '\n\n' +
    'Return ONLY a JSON array (no markdown, no explanation) of exactly 3 objects:\n' +
    '[{\n' +
    '  "title": "short punchy title (max 8 words)",\n' +
    '  "startSec": <number>,\n' +
    '  "endSec": <number>,\n' +
    '  "reason": "one sentence on why this is viral",\n' +
    '  "hook": "the opening words that will stop the scroll"\n' +
    '}]';

  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type':       'application/json',
      'x-api-key':          apiKey,
      'anthropic-version':  '2023-06-01',
    },
    body: JSON.stringify({
      model:      'claude-opus-4-5',
      max_tokens: 1024,
      messages:   [{ role: 'user', content: prompt }],
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error('Claude API error: ' + ((err.error && err.error.message) || res.status));
  }

  const data = await res.json();
  const raw  = (data.content && data.content[0] && data.content[0].text) || '';

  // Parse JSON — Claude may wrap it in markdown fences
  let clips;
  try {
    clips = JSON.parse(raw);
  } catch (_) {
    const match = raw.match(/\[\s*\{[\s\S]*\}\s*\]/);
    if (match) {
      clips = JSON.parse(match[0]);
    } else {
      throw new Error('Could not parse Claude response as JSON. Raw: ' + raw.slice(0, 200));
    }
  }

  if (!Array.isArray(clips) || clips.length === 0) {
    throw new Error('Claude returned no clips.');
  }

  return clips.slice(0, 3);
}

// ── Premiere cut ──────────────────────────────────────────────────
function cutClipsInPremiere(clips) {
  return new Promise(function(resolve, reject) {
    // Escape single quotes so the JSON survives inside evalScript string
    const json = JSON.stringify(clips).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    csInterface.evalScript("createViralClips('" + json + "')", function(result) {
      try {
        const r = JSON.parse(result);
        if (r.error) reject(new Error(r.error));
        else resolve(r);
      } catch (e) {
        reject(new Error('ExtendScript response error: ' + result));
      }
    });
  });
}

// ── UI helpers ────────────────────────────────────────────────────
function renderResults(clips) {
  const container = document.getElementById('clips-container');
  container.innerHTML = '';

  clips.forEach(function(clip, i) {
    const dur  = Math.round(clip.endSec - clip.startSec);
    const card = document.createElement('div');
    card.className = 'clip-card';
    card.innerHTML =
      '<div class="clip-header">' +
        '<span class="clip-badge">Clip ' + (i + 1) + '</span>' +
        '<span class="clip-title">' + escHtml(clip.title) + '</span>' +
      '</div>' +
      '<div class="clip-timestamps">' +
        '<span class="timestamp">' + formatTime(clip.startSec) + '</span>' +
        '<span style="color:var(--text-dim)">&#8594;</span>' +
        '<span class="timestamp">' + formatTime(clip.endSec) + '</span>' +
        '<span class="clip-duration">' + dur + 's</span>' +
      '</div>' +
      '<div class="clip-reason">' + escHtml(clip.reason) + '</div>' +
      '<div class="clip-hook">“' + escHtml(clip.hook) + '”</div>';
    container.appendChild(card);
  });

  document.getElementById('results').classList.remove('hidden');
}

function stepState(id, state, statusText) {
  const el = document.getElementById(id);
  el.className = 'step ' + state;
  el.querySelector('.step-status').textContent = statusText;
}

function setStatus(msg, state) {
  document.getElementById('status-text').textContent = msg;
  const dot = document.getElementById('status-dot');
  dot.className = 'status-dot ' + (state || 'idle');
}

function setProgress(pct) {
  document.getElementById('progress-bar').style.width = pct + '%';
}

function formatTime(sec) {
  const s = Math.floor(sec);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m + ':' + (r < 10 ? '0' : '') + r;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function delay(ms) {
  return new Promise(function(resolve) { setTimeout(resolve, ms); });
}
