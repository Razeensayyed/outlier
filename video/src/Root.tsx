import "./index.css";
import { Composition } from "remotion";
import { Intro } from "./Intro";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Intro"
      component={Intro}
      durationInFrames={90}
      fps={30}
      width={1280}
      height={720}
      defaultProps={{ title: "Outlier", subtitle: "Welcome" }}
    />
  );
};
