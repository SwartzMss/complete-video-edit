import {AbsoluteFill, CanvasImage, Easing, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

export type SingleEffect = {
  type: 'photo-single';
  id: string;
  startFrame: number;
  durationInFrames: number;
  photos: [string];
  layout: 'center' | 'pip';
  motion: 'none' | 'ken-burns';
  scale: number;
  position: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
  margin: number;
  zoomFactor: number;
  entryFrames: number;
  exitFrames: number;
  reviewFrames: number[];
  layer: number;
};

export const PhotoSingle = ({effect}: {effect: SingleEffect}) => {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const end = effect.durationInFrames - 1;
  // First and last frames are clean master frames, including the minimum 3-frame effect.
  const opacity = Math.max(0, Math.min(1, frame / effect.entryFrames, (end - frame) / effect.exitFrames));
  const size = effect.motion === 'ken-burns'
    ? interpolate(frame, [0, end], [effect.scale / effect.zoomFactor, effect.scale], {
      extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.quad)})
    : effect.scale;
  const pip = effect.layout === 'pip';
  // Anchor the whole contain-box in the corner; zoom stays inside its maximum bounds.
  const x = !pip ? .5 : effect.position.endsWith('left') ? effect.margin + size / 2 : 1 - effect.margin - size / 2;
  const y = !pip ? .5 : effect.position.startsWith('top') ? effect.margin + size / 2 : 1 - effect.margin - size / 2;
  return <AbsoluteFill style={{zIndex: effect.layer}}>
    {!pip && <AbsoluteFill style={{backgroundColor: '#000', opacity: .22 * opacity}} />}
    <CanvasImage src={staticFile(effect.photos[0])} premountFor={Math.ceil(fps)}
      style={{position: 'absolute', left: x * width, top: y * height, translate: '-50% -50%',
        width: size * width, height: size * height, objectFit: 'contain', opacity}} />
  </AbsoluteFill>;
};
