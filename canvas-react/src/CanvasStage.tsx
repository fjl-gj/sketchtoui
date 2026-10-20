import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import type { CanvasData, Color, LayerNode } from './types'

export type CanvasStageHandle = {
  fit: () => void
  zoom: (factor: number) => void
  focus: (node: LayerNode) => void
}

type CanvasStageProps = {
  data: CanvasData
  initialFocus?: LayerNode | null
  selected: LayerNode | null
  onSelect: (node: LayerNode | null) => void
  onHover: (node: LayerNode | null, position: { x: number; y: number } | null) => void
  onViewportChange?: (scale: number) => void
}

type Viewport = {
  scale: number
  panX: number
  panY: number
}

type WorldViewport = {
  minX: number
  minY: number
  maxX: number
  maxY: number
}

const imageCache = new Map<string, HTMLImageElement>()
const maximumPixelRatio = 2

function rgba(color?: Color) {
  if (!color) return null
  return `rgba(${Math.round((color.red ?? 0) * 255)}, ${Math.round((color.green ?? 0) * 255)}, ${Math.round((color.blue ?? 0) * 255)}, ${color.alpha ?? 1})`
}

function enabled<T extends { enabled?: boolean }>(items?: T[]) {
  return (items ?? []).filter((item) => item.enabled)
}

function parsePoint(value?: string) {
  const match = /^\{\s*([^,]+),\s*([^}]+)\}$/.exec(value ?? '')
  return match ? [Number(match[1]), Number(match[2])] : [0, 0]
}

function appendShapePath(context: CanvasRenderingContext2D, node: LayerNode, width: number, height: number, offsetX = 0, offsetY = 0) {
  const points = node.points ?? []
  if (points.length < 2) return false
  const coordinates = (value?: string) => {
    const [x, y] = parsePoint(value)
    return [x * width, y * height] as const
  }
  const first = points[0]
  const [firstX, firstY] = coordinates(first.point)
  context.moveTo(offsetX + firstX, offsetY + firstY)
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1]
    const current = points[index]
    const [targetX, targetY] = coordinates(current.point)
    const isCurve = previous.hasCurveFrom || current.hasCurveTo || previous.curveMode === 2 || current.curveMode === 2
    if (!isCurve) {
      context.lineTo(offsetX + targetX, offsetY + targetY)
      continue
    }
    const [controlOneX, controlOneY] = coordinates(previous.curveFrom ?? previous.point)
    const [controlTwoX, controlTwoY] = coordinates(current.curveTo ?? current.point)
    context.bezierCurveTo(offsetX + controlOneX, offsetY + controlOneY, offsetX + controlTwoX, offsetY + controlTwoY, offsetX + targetX, offsetY + targetY)
  }
  const last = points[points.length - 1]
  const [lastControlX, lastControlY] = coordinates(last.curveFrom ?? last.point)
  const [firstControlX, firstControlY] = coordinates(first.curveTo ?? first.point)
  if (last.hasCurveFrom || first.hasCurveTo || last.curveMode === 2 || first.curveMode === 2) context.bezierCurveTo(offsetX + lastControlX, offsetY + lastControlY, offsetX + firstControlX, offsetY + firstControlY, offsetX + firstX, offsetY + firstY)
  else context.lineTo(offsetX + firstX, offsetY + firstY)
  context.closePath()
  return true
}

function drawShapePath(context: CanvasRenderingContext2D, node: LayerNode, width: number, height: number) {
  context.beginPath()
  return appendShapePath(context, node, width, height)
}

function isVectorNode(node: LayerNode) {
  return ['shape_path', 'rectangle', 'oval'].includes(node.type)
}

function isCompoundShapeGroup(node: LayerNode, hasOwnPaint: boolean) {
  return node.type === 'shape_group' && hasOwnPaint && Boolean(node.children?.length) && node.children?.every(isVectorNode)
}

function compoundFillRule(node: LayerNode): CanvasFillRule {
  return node.style?.windingRule === 0 ? 'evenodd' : 'nonzero'
}

function flatten(nodes: LayerNode[]) {
  const all: LayerNode[] = []
  const visit = (node: LayerNode) => {
    all.push(node)
    node.children?.forEach(visit)
  }
  nodes.forEach(visit)
  return all
}

function appendRoundedRect(context: CanvasRenderingContext2D, width: number, height: number, radii?: number[], offsetX = 0, offsetY = 0) {
  const radius = Math.max(0, Math.min(width / 2, height / 2, Number(radii?.[0] ?? 0)))
  context.moveTo(offsetX + radius, offsetY)
  context.lineTo(offsetX + width - radius, offsetY)
  context.quadraticCurveTo(offsetX + width, offsetY, offsetX + width, offsetY + radius)
  context.lineTo(offsetX + width, offsetY + height - radius)
  context.quadraticCurveTo(offsetX + width, offsetY + height, offsetX + width - radius, offsetY + height)
  context.lineTo(offsetX + radius, offsetY + height)
  context.quadraticCurveTo(offsetX, offsetY + height, offsetX, offsetY + height - radius)
  context.lineTo(offsetX, offsetY + radius)
  context.quadraticCurveTo(offsetX, offsetY, offsetX + radius, offsetY)
  context.closePath()
}

function roundedRect(context: CanvasRenderingContext2D, width: number, height: number, radii?: number[]) {
  context.beginPath()
  appendRoundedRect(context, width, height, radii)
}

function hasPaint(style?: LayerNode['style']) {
  return Boolean(enabled(style?.fills).length || enabled(style?.borders).length)
}

type Fill = NonNullable<NonNullable<LayerNode['style']>['fills']>[number]
type Paint = Pick<Fill, 'type' | 'color' | 'gradient'>

const blendModes: Record<number, GlobalCompositeOperation> = {
  0: 'source-over',
  1: 'darken',
  2: 'multiply',
  3: 'color-burn',
  4: 'lighten',
  5: 'screen',
  6: 'color-dodge',
  7: 'overlay',
  8: 'soft-light',
  9: 'hard-light',
  10: 'difference',
  11: 'exclusion',
  12: 'hue',
  13: 'saturation',
  14: 'color',
  15: 'luminosity',
}

function shouldCompositeSubtree(node: LayerNode) {
  if (!node.children?.length) return false
  const style = node.style
  return Boolean(
    node.rotation
    || node.flippedHorizontal
    || node.flippedVertical
    || (style?.opacity ?? 1) < 1
    || Number(style?.blur?.radius ?? 0) > 0
    || (style?.blendMode ?? 0) !== 0,
  )
}

function loadImage(source: string, redraw: () => void) {
  let image = imageCache.get(source)
  if (!image) {
    image = new Image()
    image.onload = redraw
    image.onerror = redraw
    image.src = source
    imageCache.set(source, image)
  }
  return image
}

function drawCompositedSubtree(
  context: CanvasRenderingContext2D,
  node: LayerNode,
  redraw: () => void,
  imageBaseUrl: string | undefined,
  viewport: WorldViewport | undefined,
  inheritedShapeStyle: LayerNode['style'] | undefined,
  inheritedOpacity: number,
) {
  const transform = context.getTransform()
  const frame = visualFrame(node)
  const screenScale = Math.max(0.0001, Math.hypot(transform.a, transform.b))
  const corners = [
    transform.transformPoint({ x: frame.absoluteX, y: frame.absoluteY }),
    transform.transformPoint({ x: frame.absoluteX + frame.width, y: frame.absoluteY }),
    transform.transformPoint({ x: frame.absoluteX, y: frame.absoluteY + frame.height }),
    transform.transformPoint({ x: frame.absoluteX + frame.width, y: frame.absoluteY + frame.height }),
  ]
  const rotationPadding = node.rotation ? Math.max(frame.width, frame.height) * screenScale * 0.5 : 0
  const blurPadding = Number(node.style?.blur?.radius ?? 0) * screenScale * 3
  const padding = Math.ceil(rotationPadding + blurPadding + 4)
  const rasterLeft = Math.floor(Math.min(...corners.map((corner) => corner.x)) - padding)
  const rasterTop = Math.floor(Math.min(...corners.map((corner) => corner.y)) - padding)
  const rasterRight = Math.ceil(Math.max(...corners.map((corner) => corner.x)) + padding)
  const rasterBottom = Math.ceil(Math.max(...corners.map((corner) => corner.y)) + padding)
  const sourceCanvas = document.createElement('canvas')
  sourceCanvas.width = Math.max(1, rasterRight - rasterLeft)
  sourceCanvas.height = Math.max(1, rasterBottom - rasterTop)
  const sourceContext = sourceCanvas.getContext('2d')
  if (!sourceContext) return
  sourceContext.imageSmoothingEnabled = true
  sourceContext.imageSmoothingQuality = 'high'
  sourceContext.setTransform(transform.a, transform.b, transform.c, transform.d, transform.e - rasterLeft, transform.f - rasterTop)
  const style = node.style
  const flattened: LayerNode = {
    ...node,
    rotation: 0,
    flippedHorizontal: false,
    flippedVertical: false,
    style: { ...style, opacity: 1, blendMode: 0, blur: null },
  }
  drawNode(sourceContext, flattened, redraw, imageBaseUrl, viewport, inheritedShapeStyle, 1)

  const targetCanvas = document.createElement('canvas')
  targetCanvas.width = sourceCanvas.width
  targetCanvas.height = sourceCanvas.height
  const targetContext = targetCanvas.getContext('2d')
  if (!targetContext) return
  targetContext.imageSmoothingEnabled = true
  targetContext.imageSmoothingQuality = 'high'
  const { width, height, absoluteX, absoluteY } = node.frame
  const center = transform.transformPoint({ x: absoluteX + width / 2, y: absoluteY + height / 2 })
  targetContext.translate(center.x - rasterLeft, center.y - rasterTop)
  targetContext.rotate(((node.rotation ?? 0) * Math.PI) / 180)
  targetContext.scale(node.flippedHorizontal ? -1 : 1, node.flippedVertical ? -1 : 1)
  targetContext.translate(rasterLeft - center.x, rasterTop - center.y)
  targetContext.drawImage(sourceCanvas, 0, 0)

  const effectiveOpacity = inheritedOpacity * (style?.opacity ?? 1)
  context.save()
  context.setTransform(1, 0, 0, 1, 0, 0)
  context.globalAlpha = effectiveOpacity
  context.globalCompositeOperation = blendModes[style?.blendMode ?? 0] ?? 'source-over'
  const blurRadius = Number(style?.blur?.radius ?? 0)
  if (blurRadius > 0 && 'filter' in context) context.filter = `blur(${blurRadius * screenScale}px)`
  context.drawImage(targetCanvas, rasterLeft, rasterTop)
  context.restore()
}

function resolveFillStyle(context: CanvasRenderingContext2D, fill: Paint, width: number, height: number) {
  const gradient = fill.gradient
  if (fill.type === 1 && gradient?.stops?.length && gradient.from && gradient.to) {
    const [fromX, fromY] = parsePoint(gradient.from)
    const [toX, toY] = parsePoint(gradient.to)
    const canvasGradient = gradient.type === 1
      ? context.createRadialGradient(
        fromX * width,
        fromY * height,
        0,
        fromX * width,
        fromY * height,
        Math.max(1, Math.hypot((toX - fromX) * width, (toY - fromY) * height)),
      )
      : context.createLinearGradient(fromX * width, fromY * height, toX * width, toY * height)
    gradient.stops.forEach((stop) => canvasGradient.addColorStop(Math.max(0, Math.min(1, stop.position ?? 0)), rgba(stop.color) ?? 'rgba(0, 0, 0, 0)'))
    return canvasGradient
  }
  return rgba(fill.color) ?? '#ffffff'
}

function paintPath(context: CanvasRenderingContext2D, node: LayerNode, style = node.style, fillRule: CanvasFillRule = 'nonzero', redraw?: () => void, imageBaseUrl?: string) {
  const fills = enabled(style?.fills)
  const baseFill = fills[0]
  const fillStyle = baseFill ? resolveFillStyle(context, baseFill, node.frame.width, node.frame.height) : '#ffffff'
  for (const shadow of enabled(style?.shadows)) {
    context.save()
    context.shadowColor = rgba(shadow.color) ?? 'rgba(0, 0, 0, .2)'
    context.shadowBlur = shadow.blurRadius ?? 0
    context.shadowOffsetX = shadow.offsetX ?? 0
    context.shadowOffsetY = shadow.offsetY ?? 0
    context.fillStyle = fillStyle
    context.fill(fillRule)
    context.restore()
  }
  fills.forEach((fill) => {
    if (fill.image?.reference && redraw) {
      const source = imageBaseUrl ? `${imageBaseUrl}/${fill.image.reference}` : `/sketch/${fill.image.reference}`
      const image = loadImage(source, redraw)
      if (image.complete && image.naturalWidth) {
        context.save()
        context.globalAlpha *= fill.opacity ?? 1
        context.clip(fillRule)
        if (fill.patternFillType === 0) {
          const pattern = context.createPattern(image, 'repeat')
          if (pattern) {
            const tileScale = Math.max(0.01, fill.patternTileScale ?? 1)
            pattern.setTransform(new DOMMatrix().scale(tileScale))
            context.fillStyle = pattern
            context.fillRect(0, 0, node.frame.width, node.frame.height)
          }
        } else {
          context.drawImage(image, 0, 0, node.frame.width, node.frame.height)
        }
        context.restore()
      }
    }
    if (fill.color || fill.gradient) {
      context.save()
      context.globalAlpha *= fill.opacity ?? 1
      context.fillStyle = resolveFillStyle(context, fill, node.frame.width, node.frame.height)
      context.fill(fillRule)
      context.restore()
    }
  })
  enabled(style?.borders).forEach((border) => {
    if (!border.thickness || (!border.color && !border.gradient)) return
    context.save()
    context.globalAlpha *= border.opacity ?? 1
    context.strokeStyle = resolveFillStyle(context, border, node.frame.width, node.frame.height)
    context.lineWidth = border.thickness
    context.stroke()
    context.restore()
  })
}

function appendVectorPath(context: CanvasRenderingContext2D, node: LayerNode, offsetX = 0, offsetY = 0) {
  const { width, height } = node.frame
  if (node.type === 'shape_path') return appendShapePath(context, node, width, height, offsetX, offsetY)
  if (node.type === 'rectangle') {
    appendRoundedRect(context, width, height, node.style?.cornerRadii, offsetX, offsetY)
    return true
  }
  if (node.type === 'oval') {
    context.ellipse(offsetX + width / 2, offsetY + height / 2, width / 2, height / 2, 0, 0, Math.PI * 2)
    context.closePath()
    return true
  }
  return false
}

function appendChildVectorPath(context: CanvasRenderingContext2D, group: LayerNode, child: LayerNode) {
  return appendVectorPath(context, child, child.frame.absoluteX - group.frame.absoluteX, child.frame.absoluteY - group.frame.absoluteY)
}

function paintWithinGroupFrame(
  context: CanvasRenderingContext2D,
  node: LayerNode,
  style: LayerNode['style'],
  redraw: () => void,
  imageBaseUrl?: string,
) {
  context.beginPath()
  context.rect(0, 0, node.frame.width, node.frame.height)
  paintPath(context, node, style, 'nonzero', redraw, imageBaseUrl)
}

function drawCompoundShapeGroup(
  context: CanvasRenderingContext2D,
  node: LayerNode,
  style: LayerNode['style'],
  redraw: () => void,
  imageBaseUrl?: string,
) {
  const children = node.children ?? []
  const [base, ...operands] = children
  if (!base) return
  const subtracts = operands.filter((child) => child.booleanOperation === 1)
  const intersections = operands.filter((child) => child.booleanOperation === 2)

  if (subtracts.length) {
    context.save()
    context.beginPath()
    appendChildVectorPath(context, node, base)
    context.clip()
    context.beginPath()
    appendChildVectorPath(context, node, base)
    subtracts.forEach((child) => appendChildVectorPath(context, node, child))
    context.clip('evenodd')
    paintWithinGroupFrame(context, node, style, redraw, imageBaseUrl)
    context.restore()
    return
  }

  if (intersections.length) {
    context.save()
    ;[base, ...intersections].forEach((child) => {
      context.beginPath()
      appendChildVectorPath(context, node, child)
      context.clip()
    })
    paintWithinGroupFrame(context, node, style, redraw, imageBaseUrl)
    context.restore()
    return
  }

  context.beginPath()
  children.forEach((child) => appendChildVectorPath(context, node, child))
  paintPath(context, node, style, compoundFillRule(node), redraw, imageBaseUrl)
}

function intersectsViewport(node: LayerNode, viewport?: WorldViewport) {
  if (!viewport) return true
  const frame = visualFrame(node)
  return frame.absoluteX + frame.width >= viewport.minX
    && frame.absoluteX <= viewport.maxX
    && frame.absoluteY + frame.height >= viewport.minY
    && frame.absoluteY <= viewport.maxY
}

type TextRun = NonNullable<NonNullable<LayerNode['text']>['runs']>[number]

type TextSegment = {
  content: string
  run: TextRun
}

function setTextFont(context: CanvasRenderingContext2D, run: TextRun | undefined, fallbackHeight: number) {
  const fontSize = run?.font?.size ?? Math.max(12, fallbackHeight)
  const fontFamily = run?.font?.cssFamily ?? run?.font?.name ?? 'sans-serif'
  const fontWeight = run?.font?.weight ?? 400
  context.font = `${fontWeight} ${fontSize}px "${fontFamily}", "PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI Emoji", sans-serif`
  return fontSize
}

function resolvedLineHeight(run: TextRun | undefined, fontSize: number, frameHeight: number, lineCount: number) {
  const configured = run?.lineHeight ?? fontSize * 1.25
  return lineCount > 1 && configured >= frameHeight ? frameHeight / lineCount : configured
}

function textSegmentsForLine(content: string, lineStart: number, lineEnd: number, runs: TextRun[]): TextSegment[] {
  const segments: TextSegment[] = []
  for (const run of runs) {
    const start = Math.max(lineStart, run.location ?? 0)
    const end = Math.min(lineEnd, (run.location ?? 0) + (run.length ?? content.length))
    if (end > start) segments.push({ content: content.slice(start, end), run })
  }
  if (segments.length === 0 && lineStart < lineEnd) segments.push({ content: content.slice(lineStart, lineEnd), run: runs[0] ?? {} })
  return segments
}

function measureTextSegment(context: CanvasRenderingContext2D, segment: TextSegment, fallbackHeight: number) {
  setTextFont(context, segment.run, fallbackHeight)
  const kerning = segment.run.kerning ?? 0
  return context.measureText(segment.content).width + Math.max(0, segment.content.length - 1) * kerning
}

function fillTextSegment(context: CanvasRenderingContext2D, segment: TextSegment, x: number, baselineY: number, fallbackHeight: number) {
  setTextFont(context, segment.run, fallbackHeight)
  context.fillStyle = rgba(segment.run.color) ?? '#111827'
  const kerning = segment.run.kerning ?? 0
  if (!kerning) {
    context.fillText(segment.content, x, baselineY)
    return context.measureText(segment.content).width
  }
  let cursor = x
  for (const character of segment.content) {
    context.fillText(character, cursor, baselineY)
    cursor += context.measureText(character).width + kerning
  }
  return cursor - x - kerning
}

function transformText(content: string, transform: TextRun['textTransform']) {
  if (typeof transform !== 'string') return content
  if (transform.toLowerCase() === 'uppercase') return content.toUpperCase()
  if (transform.toLowerCase() === 'lowercase') return content.toLowerCase()
  if (transform.toLowerCase() === 'capitalize') return content.replace(/(^|\s)(\S)/g, (_, prefix, character) => `${prefix}${character.toUpperCase()}`)
  return content
}

function drawTextNode(context: CanvasRenderingContext2D, node: LayerNode, width: number, height: number) {
  const content = String(node.text?.content ?? '')
  if (!content) return
  const runs = node.text?.runs?.length ? node.text.runs : [{}]
  const lines = content.split('\n')
  const firstRun = runs[0]
  const defaultFontSize = setTextFont(context, firstRun, height)
  const lineHeights = lines.map(() => resolvedLineHeight(firstRun, defaultFontSize, height, lines.length))
  const textBlockHeight = lineHeights.reduce((total, lineHeight) => total + lineHeight, 0)
  const verticalAlignment = firstRun?.verticalAlignment ?? 0
  const textBlockTop = verticalAlignment === 1
    ? (height - textBlockHeight) / 2
    : verticalAlignment === 2
      ? height - textBlockHeight
      : 0
  const alignment = firstRun?.alignment ?? 0

  context.save()
  context.beginPath()
  context.rect(0, 0, width, height)
  context.clip()
  context.textBaseline = 'alphabetic'
  let lineStart = 0
  let lineTop = textBlockTop
  lines.forEach((line, lineIndex) => {
    const segments = textSegmentsForLine(content, lineStart, lineStart + line.length, runs)
      .map((segment) => ({ ...segment, content: transformText(segment.content, segment.run.textTransform) }))
    const lineHeight = lineHeights[lineIndex]
    const lineWidth = segments.reduce((total, segment) => total + measureTextSegment(context, segment, height), 0)
    const x = alignment === 1 ? (width - lineWidth) / 2 : alignment === 2 ? width - lineWidth : 0
    const firstSegment = segments[0]
    const fontSize = setTextFont(context, firstSegment?.run, height)
    const metrics = context.measureText(firstSegment?.content || '国Ag')
    const ascent = metrics.actualBoundingBoxAscent || fontSize * 0.8
    const descent = metrics.actualBoundingBoxDescent || fontSize * 0.2
    const baselineY = lineTop + (lineHeight - ascent - descent) / 2 + ascent
    let cursor = x
    segments.forEach((segment) => { cursor += fillTextSegment(context, segment, cursor, baselineY, height) })
    lineStart += line.length + 1
    lineTop += lineHeight
  })
  context.restore()
}

function applyNodeClip(context: CanvasRenderingContext2D, node: LayerNode) {
  const { width, height, absoluteX, absoluteY } = node.frame
  const rotation = ((node.rotation ?? 0) * Math.PI) / 180
  context.translate(absoluteX + width / 2, absoluteY + height / 2)
  context.rotate(rotation)
  context.scale(node.flippedHorizontal ? -1 : 1, node.flippedVertical ? -1 : 1)
  context.translate(-width / 2, -height / 2)
  if (node.type === 'shape_path' && node.points?.length) {
    drawShapePath(context, node, width, height)
  } else if (node.type === 'oval') {
    context.beginPath()
    appendVectorPath(context, node)
  } else {
    roundedRect(context, width, height, node.style?.cornerRadii)
  }
  context.clip()
  context.translate(width / 2, height / 2)
  context.scale(node.flippedHorizontal ? -1 : 1, node.flippedVertical ? -1 : 1)
  context.rotate(-rotation)
  context.translate(-absoluteX - width / 2, -absoluteY - height / 2)
}

function drawChildren(
  context: CanvasRenderingContext2D,
  children: LayerNode[] | undefined,
  redraw: () => void,
  imageBaseUrl: string | undefined,
  viewport: WorldViewport | undefined,
  inheritedShapeStyle: LayerNode['style'] | undefined,
  inheritedOpacity: number,
) {
  let activeMask: LayerNode | null = null
  children?.forEach((child) => {
    if (child.breaksMaskChain) activeMask = null
    if (child.isMask) {
      drawNode(context, child, redraw, imageBaseUrl, viewport, inheritedShapeStyle, inheritedOpacity)
      activeMask = child
      return
    }
    if (!activeMask) {
      drawNode(context, child, redraw, imageBaseUrl, viewport, inheritedShapeStyle, inheritedOpacity)
      return
    }
    context.save()
    applyNodeClip(context, activeMask)
    drawNode(context, child, redraw, imageBaseUrl, viewport, inheritedShapeStyle, inheritedOpacity)
    context.restore()
  })
}

function drawNode(
  context: CanvasRenderingContext2D,
  node: LayerNode,
  redraw: () => void,
  imageBaseUrl?: string,
  viewport?: WorldViewport,
  inheritedShapeStyle?: LayerNode['style'],
  inheritedOpacity = 1,
) {
  if (node.visible === false || !intersectsViewport(node, viewport)) return
  if (shouldCompositeSubtree(node)) {
    drawCompositedSubtree(context, node, redraw, imageBaseUrl, viewport, inheritedShapeStyle, inheritedOpacity)
    return
  }
  const { width, height, absoluteX, absoluteY } = node.frame
  const ownStyle = node.style
  const ownHasPaint = hasPaint(ownStyle)
  const compoundShapeGroup = isCompoundShapeGroup(node, ownHasPaint)
  const effectiveShapeStyle = node.type === 'shape_path' && !ownHasPaint ? inheritedShapeStyle : ownStyle
  const effectiveOpacity = inheritedOpacity * (ownStyle?.opacity ?? 1)
  context.save()
  context.globalAlpha = effectiveOpacity
  context.globalCompositeOperation = blendModes[ownStyle?.blendMode ?? 0] ?? 'source-over'
  const blurRadius = Number(ownStyle?.blur?.radius ?? 0)
  if (blurRadius > 0 && 'filter' in context) context.filter = `blur(${blurRadius}px)`
  context.translate(absoluteX + width / 2, absoluteY + height / 2)
  context.rotate(((node.rotation ?? 0) * Math.PI) / 180)
  context.scale(node.flippedHorizontal ? -1 : 1, node.flippedVertical ? -1 : 1)
  context.translate(-width / 2, -height / 2)

  if (node.type === 'design_page') {
    if (ownHasPaint) {
      roundedRect(context, width, height, ownStyle?.cornerRadii)
      paintPath(context, node, ownStyle, 'nonzero', redraw, imageBaseUrl)
    } else {
      roundedRect(context, width, height, ownStyle?.cornerRadii)
      context.fillStyle = '#ffffff'
      context.fill()
    }
    context.save()
    roundedRect(context, width, height, node.style?.cornerRadii)
    context.strokeStyle = 'rgba(41, 62, 88, .38)'
    context.lineWidth = 1
    context.stroke()
    context.restore()
  } else if (['group', 'rectangle'].includes(node.type)) {
    if (ownHasPaint) {
      roundedRect(context, width, height, ownStyle?.cornerRadii)
      paintPath(context, node, ownStyle, 'nonzero', redraw, imageBaseUrl)
    }
  } else if (node.type === 'oval' && ownHasPaint) {
    context.beginPath()
    appendVectorPath(context, node)
    paintPath(context, node, ownStyle, 'nonzero', redraw, imageBaseUrl)
  }

  if (compoundShapeGroup) drawCompoundShapeGroup(context, node, ownStyle, redraw, imageBaseUrl)

  if (node.type === 'shape_path' && node.points?.length) {
    if (drawShapePath(context, node, width, height)) paintPath(context, node, effectiveShapeStyle, 'nonzero', redraw, imageBaseUrl)
  }

  if (node.type === 'text') drawTextNode(context, node, width, height)

  if (node.type === 'image' && node.image?.reference) {
    const source = imageBaseUrl ? `${imageBaseUrl}/${node.image.reference}` : `/sketch/${node.image.reference}`
    const image = loadImage(source, redraw)
    if (image.complete && image.naturalWidth) context.drawImage(image, 0, 0, width, height)
    else {
      context.fillStyle = '#d9e1ea'
      context.fillRect(0, 0, width, height)
    }
  }

  const childShapeStyle = node.type === 'shape_group' && ownHasPaint ? ownStyle : inheritedShapeStyle
  context.restore()
  if (!compoundShapeGroup) {
    if (node.type === 'design_page') {
      context.save()
      applyNodeClip(context, node)
      drawChildren(context, node.children, redraw, imageBaseUrl, viewport, childShapeStyle, effectiveOpacity)
      context.restore()
    } else {
      drawChildren(context, node.children, redraw, imageBaseUrl, viewport, childShapeStyle, effectiveOpacity)
    }
  }
}

function drawArtboardSurface(context: CanvasRenderingContext2D, node: LayerNode, viewport?: WorldViewport) {
  if (!intersectsViewport(node, viewport)) return
  const { absoluteX, absoluteY, width, height } = node.frame
  context.save()
  context.fillStyle = '#ffffff'
  context.fillRect(absoluteX, absoluteY, width, height)
  context.strokeStyle = 'rgba(41, 62, 88, .44)'
  context.lineWidth = 1
  context.strokeRect(absoluteX, absoluteY, width, height)
  context.restore()
}

function visualFrame(node: LayerNode) {
  return node.type === 'design_page' ? node.frame : node.visualFrame ?? node.frame
}

function drawOutline(context: CanvasRenderingContext2D, node: LayerNode | null, scale: number, color: string, fill: string) {
  if (!node) return
  const { absoluteX, absoluteY, width, height } = visualFrame(node)
  context.save()
  context.setLineDash([6 / scale, 4 / scale])
  context.lineWidth = 2 / scale
  context.strokeStyle = color
  context.fillStyle = fill
  context.fillRect(absoluteX, absoluteY, width, height)
  context.strokeRect(absoluteX, absoluteY, width, height)
  context.restore()
}

function containingDesignPage(node: LayerNode, designPages: LayerNode[]) {
  const frame = visualFrame(node)
  const centerX = frame.absoluteX + frame.width / 2
  const centerY = frame.absoluteY + frame.height / 2
  return designPages
    .filter((page) => {
      const pageFrame = visualFrame(page)
      return centerX >= pageFrame.absoluteX
        && centerX <= pageFrame.absoluteX + pageFrame.width
        && centerY >= pageFrame.absoluteY
        && centerY <= pageFrame.absoluteY + pageFrame.height
    })
    .sort((left, right) => visualFrame(left).width * visualFrame(left).height - visualFrame(right).width * visualFrame(right).height)[0]
}

function drawMeasurementLabel(context: CanvasRenderingContext2D, text: string, centerX: number, topY: number, scale: number) {
  const fontSize = 12 / scale
  const horizontalPadding = 6 / scale
  const height = 21 / scale
  context.save()
  context.font = `600 ${fontSize}px Inter, "PingFang SC", "Microsoft YaHei", sans-serif`
  context.textBaseline = 'middle'
  const width = context.measureText(text).width + horizontalPadding * 2
  context.fillStyle = 'rgba(255, 255, 255, .96)'
  context.fillRect(centerX - width / 2, topY, width, height)
  context.fillStyle = '#147de0'
  context.fillText(text, centerX - width / 2 + horizontalPadding, topY + height / 2)
  context.restore()
}

function drawSelectionMeasurements(context: CanvasRenderingContext2D, node: LayerNode | null, designPages: LayerNode[], scale: number) {
  if (!node) return
  const frame = visualFrame(node)
  const pageFrame = visualFrame(containingDesignPage(node, designPages) ?? node)
  const lineInset = 7 / scale
  const labelGap = 8 / scale
  context.save()
  context.strokeStyle = '#1684ef'
  context.setLineDash([4 / scale, 3 / scale])
  context.lineWidth = 1 / scale
  context.beginPath()
  context.moveTo(frame.absoluteX, pageFrame.absoluteY)
  context.lineTo(frame.absoluteX, pageFrame.absoluteY + pageFrame.height)
  context.moveTo(frame.absoluteX + frame.width, pageFrame.absoluteY)
  context.lineTo(frame.absoluteX + frame.width, pageFrame.absoluteY + pageFrame.height)
  context.moveTo(pageFrame.absoluteX, frame.absoluteY)
  context.lineTo(pageFrame.absoluteX + pageFrame.width, frame.absoluteY)
  context.moveTo(pageFrame.absoluteX, frame.absoluteY + frame.height)
  context.lineTo(pageFrame.absoluteX + pageFrame.width, frame.absoluteY + frame.height)
  context.stroke()
  context.setLineDash([])
  context.lineWidth = 1.5 / scale
  context.strokeRect(frame.absoluteX, frame.absoluteY, frame.width, frame.height)
  context.fillStyle = '#ffffff'
  context.strokeStyle = '#1684ef'
  const handleSize = 6 / scale
  for (const [x, y] of [[frame.absoluteX, frame.absoluteY], [frame.absoluteX + frame.width, frame.absoluteY], [frame.absoluteX, frame.absoluteY + frame.height], [frame.absoluteX + frame.width, frame.absoluteY + frame.height]]) {
    context.fillRect(x - handleSize / 2, y - handleSize / 2, handleSize, handleSize)
    context.strokeRect(x - handleSize / 2, y - handleSize / 2, handleSize, handleSize)
  }
  context.restore()
  drawMeasurementLabel(context, `${Math.round(frame.width)} px`, frame.absoluteX + frame.width / 2, frame.absoluteY - labelGap - 21 / scale, scale)
  drawMeasurementLabel(context, `${Math.round(frame.height)} px`, frame.absoluteX - lineInset - 32 / scale, frame.absoluteY + frame.height / 2 - 10 / scale, scale)
}

export const CanvasStage = forwardRef<CanvasStageHandle, CanvasStageProps>(function CanvasStage(
  { data, initialFocus, selected, onSelect, onHover, onViewportChange },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const viewportRef = useRef<Viewport>({ scale: 1, panX: 0, panY: 0 })
  const dragRef = useRef<{ x: number; y: number; panX: number; panY: number; moved: boolean } | null>(null)
  const drawFrameRef = useRef<number | null>(null)
  const viewportAnimationRef = useRef<number | null>(null)
  const hoverFrameRef = useRef<number | null>(null)
  const pendingHoverRef = useRef<{ node: LayerNode | null; position: { x: number; y: number } | null } | null>(null)
  const reportedScaleRef = useRef<number | null>(null)
  const [hovered, setHovered] = useState<LayerNode | null>(null)
  const selectedRef = useRef(selected)
  const onHoverRef = useRef(onHover)
  const onViewportChangeRef = useRef(onViewportChange)
  const fitFrameRef = useRef<(frame: { absoluteX: number; absoluteY: number; width: number; height: number }) => void>(() => undefined)
  selectedRef.current = selected
  onHoverRef.current = onHover
  onViewportChangeRef.current = onViewportChange

  const center = useCallback(() => {
    const element = containerRef.current
    return { x: (element?.clientWidth ?? 0) / 2, y: (element?.clientHeight ?? 0) / 2 }
  }, [])

  const worldCenter = useCallback(() => ({
    x: (data.bounds.minX + data.bounds.maxX) / 2,
    y: (data.bounds.minY + data.bounds.maxY) / 2,
  }), [data.bounds])

  const hitTestNodes = useMemo(() => flatten(data.designPages).reverse(), [data.designPages])

  const draw = useCallback(() => {
    if (drawFrameRef.current !== null) return
    drawFrameRef.current = window.requestAnimationFrame(() => {
      drawFrameRef.current = null
      const canvas = canvasRef.current
      const container = containerRef.current
      if (!canvas || !container) return
      const context = canvas.getContext('2d')
      if (!context) return
      const ratio = Math.min(window.devicePixelRatio || 1, maximumPixelRatio)
      const width = Math.max(1, Math.round(container.clientWidth * ratio))
      const height = Math.max(1, Math.round(container.clientHeight * ratio))
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width
        canvas.height = height
      }
      context.imageSmoothingEnabled = true
      context.imageSmoothingQuality = 'high'
      context.setTransform(1, 0, 0, 1, 0, 0)
      context.clearRect(0, 0, canvas.width, canvas.height)
      const view = viewportRef.current
      if (reportedScaleRef.current === null || Math.abs(reportedScaleRef.current - view.scale) > 0.0001) {
        reportedScaleRef.current = view.scale
        onViewportChangeRef.current?.(view.scale)
      }
      const canvasCenter = center()
      const world = worldCenter()
      const overscan = 96 / view.scale
      const viewport: WorldViewport = {
        minX: world.x + (-canvasCenter.x - view.panX) / view.scale - overscan,
        minY: world.y + (-canvasCenter.y - view.panY) / view.scale - overscan,
        maxX: world.x + (container.clientWidth - canvasCenter.x - view.panX) / view.scale + overscan,
        maxY: world.y + (container.clientHeight - canvasCenter.y - view.panY) / view.scale + overscan,
      }
      context.setTransform(
        ratio * view.scale,
        0,
        0,
        ratio * view.scale,
        (canvasCenter.x + view.panX - world.x * view.scale) * ratio,
        (canvasCenter.y + view.panY - world.y * view.scale) * ratio,
      )
      data.designPages.forEach((node) => drawArtboardSurface(context, node, viewport))
      data.designPages.forEach((node) => drawNode(context, node, draw, data.imageBaseUrl, viewport))
      if (hovered && hovered !== selectedRef.current) drawOutline(context, hovered, view.scale, '#f5b700', 'rgba(245, 183, 0, .12)')
      drawSelectionMeasurements(context, selectedRef.current, data.designPages, view.scale)
    })
  }, [center, data.designPages, hovered, worldCenter])

  const cancelViewportAnimation = useCallback(() => {
    if (viewportAnimationRef.current !== null) {
      window.cancelAnimationFrame(viewportAnimationRef.current)
      viewportAnimationRef.current = null
    }
  }, [])

  const fitFrame = useCallback((frame: { absoluteX: number; absoluteY: number; width: number; height: number }) => {
    const container = containerRef.current
    if (!container) return
    cancelViewportAnimation()
    const viewportWidth = Math.max(320, container.clientWidth - 96)
    const viewportHeight = Math.max(320, container.clientHeight - 96)
    const scale = Math.min(
      viewportWidth / Math.max(1, frame.width),
      viewportHeight / Math.max(1, frame.height),
      1,
    )
    const targetX = frame.absoluteX + frame.width / 2
    const targetY = frame.absoluteY + frame.height / 2
    const world = worldCenter()
    viewportRef.current.scale = scale
    viewportRef.current.panX = (world.x - targetX) * scale
    viewportRef.current.panY = (world.y - targetY) * scale
    draw()
  }, [cancelViewportAnimation, draw, worldCenter])

  const fit = useCallback(() => {
    fitFrame({ absoluteX: data.bounds.minX, absoluteY: data.bounds.minY, width: data.bounds.width, height: data.bounds.height })
  }, [data.bounds, fitFrame])

  const focus = useCallback((node: LayerNode) => {
    const frame = visualFrame(node)
    const targetX = frame.absoluteX + frame.width / 2
    const targetY = frame.absoluteY + frame.height / 2
    const world = worldCenter()
    const view = viewportRef.current
    const startPanX = view.panX
    const startPanY = view.panY
    const targetPanX = (world.x - targetX) * view.scale
    const targetPanY = (world.y - targetY) * view.scale
    const startedAt = performance.now()
    const duration = 180
    cancelViewportAnimation()
    const animate = (now: number) => {
      const progress = Math.min(1, (now - startedAt) / duration)
      const eased = 1 - (1 - progress) ** 3
      view.panX = startPanX + (targetPanX - startPanX) * eased
      view.panY = startPanY + (targetPanY - startPanY) * eased
      draw()
      if (progress < 1) viewportAnimationRef.current = window.requestAnimationFrame(animate)
      else viewportAnimationRef.current = null
    }
    viewportAnimationRef.current = window.requestAnimationFrame(animate)
  }, [cancelViewportAnimation, draw, worldCenter])

  fitFrameRef.current = fitFrame

  const zoom = useCallback((factor: number) => {
    const canvas = canvasRef.current
    if (!canvas) return
    cancelViewportAnimation()
    const rect = canvas.getBoundingClientRect()
    const clientX = rect.left + rect.width / 2
    const clientY = rect.top + rect.height / 2
    const point = screenToWorld(clientX, clientY)
    const view = viewportRef.current
    view.scale = Math.max(0.05, Math.min(3, view.scale * factor))
    const viewCenter = center()
    const world = worldCenter()
    view.panX = viewCenter.x - (point.x - world.x) * view.scale - viewCenter.x
    view.panY = viewCenter.y - (point.y - world.y) * view.scale - viewCenter.y
    draw()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cancelViewportAnimation, center, draw, worldCenter])

  const screenToWorld = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current
    if (!canvas) return { x: 0, y: 0 }
    const rect = canvas.getBoundingClientRect()
    const view = viewportRef.current
    const canvasCenter = center()
    const world = worldCenter()
    return {
      x: world.x + (clientX - rect.left - canvasCenter.x - view.panX) / view.scale,
      y: world.y + (clientY - rect.top - canvasCenter.y - view.panY) / view.scale,
    }
  }, [center, worldCenter])

  const hitTest = useCallback((clientX: number, clientY: number) => {
    const point = screenToWorld(clientX, clientY)
    return hitTestNodes.find((node) => {
      if (node.visible === false) return false
      const frame = visualFrame(node)
      return point.x >= frame.absoluteX
        && point.x <= frame.absoluteX + frame.width
        && point.y >= frame.absoluteY
        && point.y <= frame.absoluteY + frame.height
    }) ?? null
  }, [hitTestNodes, screenToWorld])

  const queueHover = useCallback((node: LayerNode | null, position: { x: number; y: number } | null) => {
    pendingHoverRef.current = { node, position }
    if (hoverFrameRef.current !== null) return
    hoverFrameRef.current = window.requestAnimationFrame(() => {
      hoverFrameRef.current = null
      const pending = pendingHoverRef.current
      pendingHoverRef.current = null
      if (pending) onHoverRef.current(pending.node, pending.position)
    })
  }, [])

  useImperativeHandle(ref, () => ({ fit, zoom, focus }), [fit, focus, zoom])

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const target = initialFocus ?? data.designPages[0]
      if (target) fitFrameRef.current(visualFrame(target))
      else fitFrameRef.current({ absoluteX: data.bounds.minX, absoluteY: data.bounds.minY, width: data.bounds.width, height: data.bounds.height })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [data.sketchPage.id, data.bounds, data.designPages, initialFocus?.id])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return undefined
    const observer = new ResizeObserver(draw)
    observer.observe(container)
    window.addEventListener('resize', draw)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', draw)
    }
  }, [draw])

  useEffect(() => {
    draw()
  }, [draw, selected])

  useEffect(() => () => {
    if (drawFrameRef.current !== null) {
      window.cancelAnimationFrame(drawFrameRef.current)
      drawFrameRef.current = null
    }
    if (viewportAnimationRef.current !== null) {
      window.cancelAnimationFrame(viewportAnimationRef.current)
      viewportAnimationRef.current = null
    }
    if (hoverFrameRef.current !== null) {
      window.cancelAnimationFrame(hoverFrameRef.current)
      hoverFrameRef.current = null
    }
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return undefined

    const handleWheel = (event: WheelEvent) => {
      if (event.cancelable) event.preventDefault()
      event.stopPropagation()
      cancelViewportAnimation()

      const view = viewportRef.current
      const rect = canvas.getBoundingClientRect()
      const pointerX = event.clientX - rect.left
      const pointerY = event.clientY - rect.top
      const canvasCenter = center()
      const world = worldCenter()
      const point = screenToWorld(event.clientX, event.clientY)

      const delta = event.deltaMode === WheelEvent.DOM_DELTA_LINE ? event.deltaY * 16 : event.deltaY
      view.scale = Math.max(0.05, Math.min(3, view.scale * Math.exp(-delta * 0.0015)))
      view.panX = pointerX - canvasCenter.x - (point.x - world.x) * view.scale
      view.panY = pointerY - canvasCenter.y - (point.y - world.y) * view.scale
      draw()
    }

    canvas.addEventListener('wheel', handleWheel, { passive: false })
    return () => canvas.removeEventListener('wheel', handleWheel)
  }, [cancelViewportAnimation, center, draw, screenToWorld, worldCenter])

  return (
    <div className="canvas-stage" ref={containerRef}>
      <canvas
        className="canvas-stage__surface"
        ref={canvasRef}
        tabIndex={0}
        aria-label="Sketch 设计画布。使用加号、减号缩放，按 0 适应窗口。"
        onKeyDown={(event) => {
          if (event.key === '0') {
            event.preventDefault()
            fit()
          } else if (event.key === '+' || event.key === '=') {
            event.preventDefault()
            zoom(1.15)
          } else if (event.key === '-') {
            event.preventDefault()
            zoom(1 / 1.15)
          }
        }}
        onPointerDown={(event) => {
          cancelViewportAnimation()
          event.currentTarget.focus()
          event.currentTarget.setPointerCapture(event.pointerId)
          dragRef.current = { x: event.clientX, y: event.clientY, panX: viewportRef.current.panX, panY: viewportRef.current.panY, moved: false }
          event.currentTarget.classList.add('dragging')
        }}
        onPointerMove={(event) => {
          const drag = dragRef.current
          if (drag) {
            const deltaX = event.clientX - drag.x
            const deltaY = event.clientY - drag.y
            drag.moved ||= Math.hypot(deltaX, deltaY) > 3
            viewportRef.current.panX = drag.panX + deltaX
            viewportRef.current.panY = drag.panY + deltaY
            draw()
            return
          }
          const node = hitTest(event.clientX, event.clientY)
          setHovered((previous) => previous?.id === node?.id ? previous : node)
          queueHover(node, { x: event.clientX, y: event.clientY })
        }}
        onPointerUp={(event) => {
          const drag = dragRef.current
          dragRef.current = null
          event.currentTarget.classList.remove('dragging')
          if (drag && !drag.moved) onSelect(hitTest(event.clientX, event.clientY))
        }}
        onPointerLeave={() => {
          if (!dragRef.current) {
            setHovered(null)
            queueHover(null, null)
          }
        }}
      />
    </div>
  )
})
