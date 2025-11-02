/**
 * @param {import("./params").Params} params - The sketch parameters
 */
export function mountSketch(params) {
  globalThis.setup = function() {
    createCanvas(400, 400);
  }

  globalThis.draw = function() {
    background(220);
    circle(mouseX, mouseY, params.size)
  }
}
