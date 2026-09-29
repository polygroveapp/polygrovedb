// focal.swift — where is the SUBJECT of each photo? (2026-09-29)
// Apple's Vision, on this Mac, no downloads: the foreground-subject mask
// ("lift subject from background") gives the subject's bounding box; photos
// where nothing lifts fall back to attention saliency (what draws the eye).
// usage: swift focal.swift <dir of .jpg> > boxes.jsonl
// one JSON line per photo: {file, w, h, box:[x,y,w,h] (fractions, origin TOP-left), how,
//   grid: G*G characters, row by row from the top — '1' where the subject is}
// The GRID is what framing is judged by: a bounding box's corners are mostly
// empty air, so testing the box flagged birds that were plainly in frame.
import Foundation
import Vision
import CoreImage

let dir = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "."
let files = (try? FileManager.default.contentsOfDirectory(atPath: dir))?.filter { $0.hasSuffix(".jpg") }.sorted() ?? []

let G = 48
// bounding box of the non-zero pixels of a one-channel mask, as fractions
// (top-left origin), and the mask itself sampled onto a G×G grid
func maskBox(_ pb: CVPixelBuffer) -> ([Double], String)? {
  CVPixelBufferLockBaseAddress(pb, .readOnly); defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
  let w = CVPixelBufferGetWidth(pb), h = CVPixelBufferGetHeight(pb), rb = CVPixelBufferGetBytesPerRow(pb)
  guard let base = CVPixelBufferGetBaseAddress(pb) else { return nil }
  let fmt = CVPixelBufferGetPixelFormatType(pb)
  var x0 = w, y0 = h, x1 = -1, y1 = -1
  for y in 0..<h {
    let row = base.advanced(by: y * rb)
    for x in 0..<w {
      let on: Bool
      if fmt == kCVPixelFormatType_OneComponent32Float { on = row.load(fromByteOffset: x * 4, as: Float32.self) > 0.5 }
      else { on = row.load(fromByteOffset: x, as: UInt8.self) > 127 }
      if on { if x < x0 { x0 = x }; if x > x1 { x1 = x }; if y < y0 { y0 = y }; if y > y1 { y1 = y } }
    }
  }
  if x1 < 0 { return nil }
  var grid = ""
  for gy in 0..<G { for gx in 0..<G {
    let x = min(w - 1, Int((Double(gx) + 0.5) / Double(G) * Double(w))), y = min(h - 1, Int((Double(gy) + 0.5) / Double(G) * Double(h)))
    let row = base.advanced(by: y * rb)
    let on = fmt == kCVPixelFormatType_OneComponent32Float ? row.load(fromByteOffset: x * 4, as: Float32.self) > 0.5 : row.load(fromByteOffset: x, as: UInt8.self) > 127
    grid += on ? "1" : "0"
  } }
  return ([Double(x0) / Double(w), Double(y0) / Double(h), Double(x1 - x0 + 1) / Double(w), Double(y1 - y0 + 1) / Double(h)], grid)
}
func boxGrid(_ b: [Double]) -> String {
  var grid = ""
  for gy in 0..<G { for gx in 0..<G {
    let x = (Double(gx) + 0.5) / Double(G), y = (Double(gy) + 0.5) / Double(G)
    grid += (x >= b[0] && x <= b[0] + b[2] && y >= b[1] && y <= b[1] + b[3]) ? "1" : "0"
  } }
  return grid
}

for f in files {
  let url = URL(fileURLWithPath: dir).appendingPathComponent(f)
  guard let ci = CIImage(contentsOf: url) else { continue }
  let W = Int(ci.extent.width), H = Int(ci.extent.height)
  let handler = VNImageRequestHandler(ciImage: ci, options: [:])
  var box: [Double]? = nil, how = "none", grid = ""
  let fg = VNGenerateForegroundInstanceMaskRequest()
  if (try? handler.perform([fg])) != nil, let obs = fg.results?.first, !obs.allInstances.isEmpty,
     let mask = try? obs.generateScaledMaskForImage(forInstances: obs.allInstances, from: handler),
     let (b, g) = maskBox(mask) {
    // a "subject" that is nearly the whole frame is the scene, not a subject
    if b[2] * b[3] < 0.92 { box = b; grid = g; how = "subject" }
  }
  if box == nil {
    let sal = VNGenerateAttentionBasedSaliencyImageRequest()
    if (try? handler.perform([sal])) != nil, let o = sal.results?.first, let objs = o.salientObjects, !objs.isEmpty {
      var u = objs[0].boundingBox
      for s in objs.dropFirst() { u = u.union(s.boundingBox) }
      box = [Double(u.minX), Double(1 - u.maxY), Double(u.width), Double(u.height)]   // Vision's origin is bottom-left
      grid = boxGrid(box!); how = "attention"
    }
  }
  let b = box ?? [0, 0, 1, 1]
  if grid.isEmpty { grid = boxGrid(b) }
  let js = String(format: "{\"file\":\"%@\",\"w\":%d,\"h\":%d,\"box\":[%.4f,%.4f,%.4f,%.4f],\"how\":\"%@\",\"grid\":\"%@\"}", f, W, H, b[0], b[1], b[2], b[3], how, grid)
  print(js)
}
