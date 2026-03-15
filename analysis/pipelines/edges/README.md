# edges pipeline

Runs Canny edge detection and extracts contours from sketch images. Parameters were tuned interactively in `playground/canny_edge_fence.py`.

## Input

Any image in `site/sketches/<sketch>/assets/`.

## Output

`<image-stem>.edges.json` written to `site/sketches/<sketch>/assets/`.

## TypeScript interface

```typescript
interface EdgesOutput {
  version: 1;
  /** source image width in pixels */
  width: number;
  /** source image height in pixels */
  height: number;
  params: {
    blur: number;
    low: number;
    high: number;
  };
  /**
   * Each contour is a list of [x, y] pixel coordinates.
   * Coordinates are in the source image's pixel space (origin top-left).
   */
  contours: [number, number][][];
}
```

## Usage

```bash
uv run analysis run edges fence-torn-paper
uv run analysis run edges fence-torn-paper --image fence-torn-paper
```
