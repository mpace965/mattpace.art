/**
 * @param {import("./params").Params} params - The sketch parameters
 */
export function mountSketch(params) {
  window.setup = function() {
    createCanvas(400, 400);
  }

  window.draw = function() {
    background(220);
    circle(mouseX, mouseY, params.size)
  }
}
