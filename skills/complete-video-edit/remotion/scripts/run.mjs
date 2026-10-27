import {readFile, mkdir} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {bundle} from '@remotion/bundler';
import {ensureBrowser, selectComposition, renderMedia, renderStill} from '@remotion/renderer';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const [mode, workspaceArg, outputArg, startArg, endArg, ...flags] = process.argv.slice(2);
if (!['studio', 'render'].includes(mode) || !workspaceArg) {
  throw new Error('Usage: node scripts/run.mjs studio WORKSPACE | render WORKSPACE OUTPUT START END [--stills]');
}
const workspace = path.resolve(workspaceArg);
const renderOutput = outputArg ? path.resolve(outputArg) : null;
const propsPath = path.join(workspace, 'props.json');
const props = JSON.parse(await readFile(propsPath, 'utf8'));
const entry = path.join(project, 'src/index.ts');
const publicDir = path.join(workspace, 'public');
process.chdir(project);

if (mode === 'studio') {
  const cli = path.join(project, 'node_modules/@remotion/cli/remotion-cli.js');
  const child = spawn(process.execPath, [cli, 'studio', entry, '--public-dir', publicDir,
    '--props', propsPath, '--no-open'], {cwd: project, stdio: 'inherit'});
  child.on('error', (error) => {console.error(error); process.exitCode = 1;});
  child.on('exit', (code) => {process.exitCode = code ?? 1;});
} else {
  const start = Number(startArg), end = Number(endArg);
  if (!renderOutput || !Number.isInteger(start) || !Number.isInteger(end) || start < 0 ||
      end <= start || end > props.durationInFrames) throw new Error('Invalid half-open render range');
  const browser = await ensureBrowser({browserExecutable: process.env.REMOTION_BROWSER_EXECUTABLE || undefined,
    onBrowserDownload: () => {throw new Error('Rendering browser missing: run npm run browser once in the Remotion project.');}});
  if (!('path' in browser)) throw new Error('Rendering browser unavailable');
  const browserExecutable = browser.path;
  const serveUrl = await bundle({entryPoint: entry, publicDir});
  const inputProps = {...props, muted: true};
  // Keep the exact timebase: Remotion's shared-memory path rounds numeric fps.
  const {timeline} = JSON.parse(await readFile(path.join(workspace, 'workspace.json'), 'utf8'));
  const composition = await selectComposition({serveUrl, id: 'PhotoPair', inputProps, browserExecutable});
  await renderMedia({composition, serveUrl, inputProps, codec: 'h264', pixelFormat: 'yuv420p',
    // Convert screenshot RGB/JPEG to limited-range YUV consistently on every OS.
    colorSpace: 'bt709',
    ffmpegOverride: ({args}) => args.map((value, index) =>
      ['-r', '-framerate'].includes(args[index - 1]) ? timeline.fps : value),
    crf: 18, muted: true, outputLocation: renderOutput, frameRange: [start, end - 1],
    concurrency: 2, browserExecutable});
  if (flags.includes('--stills')) {
    const frames = new Set([start, end - 1]);
    for (const effect of props.effects) {
      if (effect.type === 'photo-single') {
        for (const offset of effect.reviewFrames) {
          const frame = effect.startFrame + offset;
          if (frame >= start && frame < end) frames.add(frame);
        }
        continue;
      }
      // Legacy prepared pair workspaces have no type/reviewFrames fields.
      const [entryFrames, overview, zoom, firstHold, swap, secondHold] = effect.phaseFrames;
      const overviewEnd = effect.startFrame + entryFrames + overview;
      const first = overviewEnd + zoom;
      const switchStart = first + firstHold;
      const second = switchStart + swap;
      for (const frame of [overviewEnd - 1, first + Math.floor(firstHold / 2),
        switchStart + Math.floor(swap / 2), second + Math.floor(secondHold / 2),
        effect.startFrame + effect.durationInFrames]) {
        if (frame >= start && frame < end) frames.add(frame);
      }
    }
    const directory = path.join(path.dirname(renderOutput), 'stills');
    await mkdir(directory, {recursive: true});
    for (const frame of [...frames].sort((a, b) => a - b)) {
      await renderStill({composition, serveUrl, inputProps, frame, imageFormat: 'png', browserExecutable,
        output: path.join(directory, `frame-${String(frame).padStart(6, '0')}.png`)});
    }
  }
}
