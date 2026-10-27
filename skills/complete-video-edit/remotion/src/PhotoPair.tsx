import {AbsoluteFill, CanvasImage, Easing, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

export type PhotoEffect = {
  type?: 'photo-pair';
  id: string;
  startFrame: number;
  durationInFrames: number;
  photos: [string, string];
  phaseFrames: [number, number, number, number, number, number, number];
  overviewScale: number;
  focusScale: number;
  layer: number;
};

// One data-driven template; photos remain complete with objectFit: contain.
export const PhotoPair = ({effect}: {effect: PhotoEffect}) => {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const [entry, overview, zoom, firstHold, swap, secondHold] = effect.phaseFrames;
  const e = entry;
  const o = e + overview;
  const z = o + zoom;
  const h = z + firstHold;
  const s = h + swap;
  const lastHold = s + secondHold;
  const finish = effect.durationInFrames;
  const options = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
    easing: Easing.bezier(.25, .1, .25, 1)} as const;
  const fade = interpolate(frame, [0, e, lastHold, finish], [0, 1, 1, 0], options);
  return <AbsoluteFill style={{zIndex: effect.layer}}>
    <AbsoluteFill style={{backgroundColor: '#000', opacity: .22 * fade}} />
    {effect.photos.map((photo, index) => {
      const begin = index === 0 ? o : h;
      const end = index === 0 ? z : s;
      const size = interpolate(frame, [begin, end], [effect.overviewScale, effect.focusScale], options);
      const x = interpolate(frame, [begin, end], [(index === 0 ? .28 : .72) * width, .5 * width], options);
      const y = interpolate(frame, [0, e, begin, end],
        [(index === 0 ? .58 : .62) * height, (index === 0 ? .48 : .52) * height,
          (index === 0 ? .48 : .52) * height, .5 * height], options);
      const opacity = index === 0
        ? interpolate(frame, [0, e, h, s], [0, 1, 1, 0], options)
        : interpolate(frame, [0, e, o, z, h, s, lastHold, finish], [0, 1, 1, 0, 0, 1, 1, 0], options);
      return <CanvasImage key={photo} src={staticFile(photo)} premountFor={Math.ceil(fps)}
        style={{position: 'absolute', left: x, top: y, translate: '-50% -50%',
          width: width * size, height: height * size, objectFit: 'contain', opacity}} />;
    })}
  </AbsoluteFill>;
};
