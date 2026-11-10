/** Decorative geometry only: never consumes a score, topic or confidence. */
export const MAP_WIDTH = 1040;
export const MAP_HEIGHT = 820;
export const MAP_PAGE_SIZE = 5;
export const MAP_CENTER = { x: 520, y: 410 };
export const ARTICLE_WIDTH = 268;
export const ARTICLE_HEIGHT = 184;

export function orbitLayout(count: number): Array<{ x: number; y: number; endX: number; endY: number; labelX: number; labelY: number; startX: number; startY: number }> {
  if (!Number.isInteger(count) || count < 0 || count > MAP_PAGE_SIZE) throw new RangeError("Orbit contains 0..5 articles");
  return Array.from({ length: count }, (_, index) => {
    const angle = -Math.PI / 2 + index * 2 * Math.PI / count;
    const dx = Math.cos(angle) * 350;
    const dy = Math.sin(angle) * 280;
    const length = Math.hypot(dx, dy);
    const ux = dx / length, uy = dy / length;
    const inset = Math.min(ARTICLE_WIDTH / 2 / Math.abs(ux), ARTICLE_HEIGHT / 2 / Math.abs(uy));
    const startX = MAP_CENTER.x + ux * 116, startY = MAP_CENTER.y + uy * 116;
    const endX = MAP_CENTER.x + dx - ux * (inset + 7), endY = MAP_CENTER.y + dy - uy * (inset + 7);
    return { x: MAP_CENTER.x + dx, y: MAP_CENTER.y + dy, startX, startY, endX, endY,
      labelX: (startX + endX) / 2, labelY: (startY + endY) / 2 };
  });
}
