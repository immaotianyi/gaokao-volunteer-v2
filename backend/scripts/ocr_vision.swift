#!/usr/bin/env swift
import Vision
import AppKit
import Foundation

// 命令行参数: image_path
guard CommandLine.arguments.count >= 2 else {
    FileHandle.standardError.write("Usage: ocr_vision <image_path>\n".data(using: .utf8)!)
    exit(1)
}
let imagePath = CommandLine.arguments[1]
guard let imageData = NSData(contentsOfFile: imagePath),
      let image = NSImage(data: imageData as Data) else {
    FileHandle.standardError.write("Failed to load image: \(imagePath)\n".data(using: .utf8)!)
    exit(1)
}

guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("Failed to get CGImage\n".data(using: .utf8)!)
    exit(1)
}

let semaphore = DispatchSemaphore(value: 0)

// 存储所有识别结果：(y_center, x_center, text)
var results: [(y: Double, x: Double, text: String)] = []

let request = VNRecognizeTextRequest { request, error in
    if let error = error {
        FileHandle.standardError.write("OCR Error: \(error)\n".data(using: .utf8)!)
        semaphore.signal()
        return
    }
    guard let observations = request.results as? [VNRecognizedTextObservation] else {
        semaphore.signal()
        return
    }
    for observation in observations {
        if let topCandidate = observation.topCandidates(1).first {
            let box = observation.boundingBox
            // Vision坐标系: origin在左下角，y从下到上
            // 转换为顶部对齐: y_top = 1 - box.origin.y - box.height
            let xCenter = Double(box.origin.x) + Double(box.width) / 2.0
            let yCenter = Double(box.origin.y) + Double(box.height) / 2.0
            results.append((y: yCenter, x: xCenter, text: topCandidate.string))
        }
    }
    semaphore.signal()
}

request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "en"]
request.usesLanguageCorrection = false  // 关闭语言校正，避免数字被错误纠正

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
do {
    try handler.perform([request])
} catch {
    FileHandle.standardError.write("Vision Error: \(error)\n".data(using: .utf8)!)
    exit(1)
}
semaphore.wait()

// 按 y 坐标分组（y相近的为同一行，容差0.02）
// Vision y轴从下到上，需要反转：用 1-y 作为从上到下的行号
let sorted = results.sorted { $0.y > $1.y }  // y大的在上（顶部）

// 聚合行
struct Row {
    var y: Double
    var cells: [(x: Double, text: String)]
}
var rows: [Row] = []
for item in sorted {
    // 查找是否有相近的行（y差 < 0.025）
    if let idx = rows.firstIndex(where: { abs($0.y - item.y) < 0.025 }) {
        rows[idx].cells.append((x: item.x, text: item.text))
        // 更新行的y为平均值
        let n = Double(rows[idx].cells.count)
        rows[idx].y = (rows[idx].y * (n - 1) + item.y) / n
    } else {
        rows.append(Row(y: item.y, cells: [(x: item.x, text: item.text)]))
    }
}

// 输出每个识别单元: y_center\tx_center\ttext
// y从大到小（从上到下），x从小到大（从左到右）
let sortedResults = results.sorted { ($0.y, $0.x) > ($1.y, $1.x) }
for item in sortedResults {
    print("\(String(format: "%.4f", item.y))\t\(String(format: "%.4f", item.x))\t\(item.text)")
}
