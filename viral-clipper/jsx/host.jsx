// ExtendScript — runs inside Premiere Pro
// ES5 only; no arrow functions, no const/let, no template literals

/**
 * Returns info about the active sequence and its first video clip file path.
 * Result is JSON string: { name, duration, fps, filePath, clips: [{filePath, start, end}] }
 */
function getSequenceInfo() {
  try {
    var app = app;
    if (!app.project || !app.project.activeSequence) {
      return JSON.stringify({ error: "No active sequence found. Please open a sequence first." });
    }

    var seq = app.project.activeSequence;
    var fps = seq.timebase ? parseFloat(seq.timebase) : 29.97;
    var durationTicks = seq.end ? seq.end.ticks : 0;
    // Premiere ticks = 254016000000 per second
    var ticksPerSec = 254016000000;
    var durationSec = durationTicks / ticksPerSec;

    var clips = [];
    var videoTracks = seq.videoTracks;

    for (var t = 0; t < videoTracks.numTracks; t++) {
      var track = videoTracks[t];
      for (var c = 0; c < track.clips.numItems; c++) {
        var clip = track.clips[c];
        var mediaPath = "";
        try {
          mediaPath = clip.projectItem.getMediaPath();
        } catch (e) {
          mediaPath = "";
        }
        var clipStartSec = clip.start.seconds;
        var clipEndSec = clip.end.seconds;
        clips.push({
          filePath: mediaPath,
          start: clipStartSec,
          end: clipEndSec,
          duration: clipEndSec - clipStartSec
        });
      }
    }

    // Use the first clip's file as the primary media file for transcription
    var primaryFilePath = clips.length > 0 ? clips[0].filePath : "";

    return JSON.stringify({
      name: seq.name,
      duration: durationSec,
      fps: fps,
      filePath: primaryFilePath,
      clips: clips
    });
  } catch (e) {
    return JSON.stringify({ error: "Error reading sequence: " + e.message });
  }
}

/**
 * Creates 3 new sequences from the viral clip timestamps.
 * viralClipsJSON: JSON string of [{title, startSec, endSec, reason}]
 * Returns JSON string: { success: true, sequences: [name, ...] } or { error }
 */
function createViralClips(viralClipsJSON) {
  try {
    var clips = JSON.parse(viralClipsJSON);
    var seq = app.project.activeSequence;
    if (!seq) {
      return JSON.stringify({ error: "No active sequence." });
    }

    var fps = 29.97;
    var ticksPerSec = 254016000000;

    var createdSequences = [];

    for (var i = 0; i < clips.length; i++) {
      var clip = clips[i];
      var newSeqName = "Viral Clip " + (i + 1) + " - " + clip.title;

      // Duplicate the active sequence
      var newSeq = seq.clone();
      if (!newSeq) {
        continue;
      }

      // Rename it
      newSeq.name = newSeqName;

      // Set in/out points to the viral clip range and perform a ripple trim
      var inPoint = new Time();
      inPoint.seconds = clip.startSec;
      var outPoint = new Time();
      outPoint.seconds = clip.endSec;

      newSeq.setPlayerPosition(inPoint.ticks);
      newSeq.setInPoint(inPoint.ticks);
      newSeq.setOutPoint(outPoint.ticks);

      // Ripple-delete everything outside the in/out range
      // Delete from outPoint to end
      var seqEnd = newSeq.end;
      if (outPoint.ticks < seqEnd.ticks) {
        newSeq.deleteRange({
          start: outPoint,
          end: newSeq.end,
          video: true,
          audio: true,
          ripple: true
        });
      }

      // Delete from start to inPoint (after adjusting for first delete)
      if (inPoint.seconds > 0) {
        var zeroTime = new Time();
        zeroTime.seconds = 0;
        var adjustedIn = new Time();
        adjustedIn.seconds = inPoint.seconds;
        newSeq.deleteRange({
          start: zeroTime,
          end: adjustedIn,
          video: true,
          audio: true,
          ripple: true
        });
      }

      createdSequences.push(newSeqName);
    }

    return JSON.stringify({ success: true, sequences: createdSequences });
  } catch (e) {
    return JSON.stringify({ error: "Error creating clips: " + e.message });
  }
}

/**
 * Opens export dialog for a named sequence.
 * Not all Premiere versions support programmatic export, so we open the dialog.
 */
function exportSequenceByName(sequenceName) {
  try {
    var sequences = app.project.sequences;
    for (var i = 0; i < sequences.numSequences; i++) {
      if (sequences[i].name === sequenceName) {
        app.project.activeSequence = sequences[i];
        app.executeCommand(app.findMenuCommandId("Export Media..."));
        return JSON.stringify({ success: true });
      }
    }
    return JSON.stringify({ error: "Sequence not found: " + sequenceName });
  } catch (e) {
    return JSON.stringify({ error: e.message });
  }
}

/**
 * Lists all sequences in the project.
 */
function listSequences() {
  try {
    var result = [];
    var sequences = app.project.sequences;
    for (var i = 0; i < sequences.numSequences; i++) {
      result.push(sequences[i].name);
    }
    return JSON.stringify({ sequences: result });
  } catch (e) {
    return JSON.stringify({ error: e.message });
  }
}
