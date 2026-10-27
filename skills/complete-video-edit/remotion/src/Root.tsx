import {Video} from '@remotion/media';
import {AbsoluteFill, Composition, Sequence, staticFile, useVideoConfig} from 'remotion';
import {PhotoPair, type PhotoEffect} from './PhotoPair';
import {PhotoSingle, type SingleEffect} from './PhotoSingle';

export type Props = {
  video: string;
  width: number;
  height: number;
  fps: number;
  durationInFrames: number;
  effects: (PhotoEffect | SingleEffect)[];
  muted: boolean;
};

export const PhotoComposition = (props: Props) => {
  const {fps} = useVideoConfig();
  return <AbsoluteFill style={{backgroundColor: '#101820'}}>
    {props.video && <Video src={staticFile(props.video)} muted={props.muted} premountFor={Math.ceil(fps)}
      style={{width: '100%', height: '100%', objectFit: 'contain'}} />}
    {props.effects.map((effect) => <Sequence key={effect.id} from={effect.startFrame}
      durationInFrames={effect.durationInFrames} premountFor={Math.ceil(fps)}>
      {effect.type === 'photo-single' ? <PhotoSingle effect={effect} /> : <PhotoPair effect={effect} />}
    </Sequence>)}
  </AbsoluteFill>;
};

export const Root = () => <Composition id="PhotoPair" component={PhotoComposition}
  width={1920} height={1080} fps={30} durationInFrames={90}
  defaultProps={{video: '', width: 1920, height: 1080, fps: 30, durationInFrames: 90, effects: [], muted: false}}
  calculateMetadata={({props}) => ({width: props.width, height: props.height, fps: props.fps,
    durationInFrames: props.durationInFrames})} />;
