// Test photos for the recipe screens, built here so no image file is kept in the repo: a PNG made
// from a gradient and a plate (a circle), in three shapes to show how a photo is cropped. The
// same bytes every time, so the saved screenshots stay the same.
import { crc32, deflateSync } from 'node:zlib';
import type { APIRequestContext } from '@playwright/test';

export type Shape = 'dish' | 'tall' | 'wide';

const SIZES: Record<Shape, [number, number, [number, number, number], [number, number, number]]> = {
  dish: [400, 300, [224, 164, 88], [122, 158, 79]],
  tall: [150, 600, [217, 130, 43], [63, 107, 140]],
  wide: [800, 150, [181, 72, 58], [232, 193, 112]],
};

function chunk(type: string, data: Buffer): Buffer {
  const head = Buffer.alloc(8);
  head.writeUInt32BE(data.length, 0);
  head.write(type, 4, 'ascii');
  const tail = Buffer.alloc(4);
  tail.writeUInt32BE(crc32(Buffer.concat([head.subarray(4), data])), 0);
  return Buffer.concat([head, data, tail]);
}

/** A PNG of the given shape: a diagonal gradient, a pale plate and a red middle. */
export function photoPng(shape: Shape): Buffer {
  const [width, height, from, to] = SIZES[shape];
  const rows: Buffer[] = [];
  const radius = Math.min(width, height) / 3;
  for (let y = 0; y < height; y++) {
    const row = Buffer.alloc(1 + width * 3); // filter byte 0, then RGB
    for (let x = 0; x < width; x++) {
      const t = (x / width + y / height) / 2;
      let rgb = from.map((c, i) => Math.round(c + (to[i]! - c) * t));
      const d = Math.hypot(x - width / 2, y - height / 2);
      if (d < radius / 2) rgb = [192, 82, 45];
      else if (d < radius) rgb = [244, 239, 228];
      row[1 + x * 3] = rgb[0]!;
      row[2 + x * 3] = rgb[1]!;
      row[3 + x * 3] = rgb[2]!;
    }
    rows.push(row);
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8; // bits
  header[9] = 2; // RGB
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', header),
    chunk('IDAT', deflateSync(Buffer.concat(rows))),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

/** Upload a test photo (as the editor does) and give back its id, to send as `photo_id`. */
export async function uploadPhoto(request: APIRequestContext, shape: Shape = 'dish'): Promise<number> {
  const response = await request.post('/api/v1/recipes/photos', {
    data: photoPng(shape),
    headers: { 'Content-Type': 'image/png' },
  });
  if (!response.ok()) throw new Error(`Photo upload → ${response.status()}: ${await response.text()}`);
  return ((await response.json()) as { id: number }).id;
}
