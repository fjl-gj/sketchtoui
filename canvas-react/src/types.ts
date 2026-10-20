export type Color = {
  red?: number
  green?: number
  blue?: number
  alpha?: number
  hex?: string
}

export type Gradient = {
  type?: number
  from?: string
  to?: string
  ellipseLength?: number
  stops?: Array<{ position?: number; color?: Color }>
}

export type LayerNode = {
  id: string
  name?: string
  type: string
  sketchClass?: string
  visible?: boolean
  locked?: boolean
  parentId?: string | null
  childCount?: number
  isMask?: boolean
  clippingMaskMode?: number
  breaksMaskChain?: boolean
  hasClickThrough?: boolean
  resizingConstraint?: number
  rotation?: number
  booleanOperation?: number
  flippedHorizontal?: boolean
  flippedVertical?: boolean
  frame: {
    x: number
    y: number
    width: number
    height: number
    absoluteX: number
    absoluteY: number
  }
  visualFrame?: {
    x: number
    y: number
    width: number
    height: number
    absoluteX: number
    absoluteY: number
  }
  style?: {
    opacity?: number
    windingRule?: number
    blendMode?: number
    fills?: Array<{ enabled?: boolean; type?: number; color?: Color; gradient?: Gradient; opacity?: number; image?: { reference?: string } | null; patternFillType?: number; patternTileScale?: number }>
    borders?: Array<{ enabled?: boolean; type?: number; color?: Color; gradient?: Gradient; thickness?: number; opacity?: number }>
    shadows?: Array<{ enabled?: boolean; color?: Color; offsetX?: number; offsetY?: number; blurRadius?: number; spread?: number }>
    blur?: { type?: number; radius?: number; saturation?: number; center?: string } | null
    cornerRadii?: number[]
  }
  text?: {
    content?: string
    runs?: Array<{
      location?: number
      length?: number
      font?: { name?: string; cssFamily?: string; size?: number; weight?: number }
      color?: Color
      alignment?: number
      lineHeight?: number | null
      verticalAlignment?: number | null
      kerning?: number | null
      textTransform?: string | number | null
      underlineStyle?: number | null
      strikethroughStyle?: number | null
    }>
  }
  image?: { reference?: string }
  symbolID?: string
  symbolMasterId?: string
  symbolMasterName?: string
  points?: Array<{ point?: string; curveFrom?: string; curveTo?: string; hasCurveFrom?: boolean; hasCurveTo?: boolean; curveMode?: number; cornerRadius?: number }>
  children?: LayerNode[]
  [key: string]: unknown
}

export type CanvasData = {
  sketchPage: { id: string; name: string }
  imageBaseUrl?: string
  bounds: { minX: number; minY: number; maxX: number; maxY: number; width: number; height: number }
  designPages: LayerNode[]
  statistics: { totalLayers: number; byType: Record<string, number> }
}

export type CanvasManifestEntry = {
  id: string
  name: string
  directory: string
  platform?: 'desktop' | 'mobile' | 'plugin'
  artboardCount: number
  layerCount: number
}

export type CanvasManifest = {
  groups: CanvasManifestEntry[]
  previews?: Array<{ name: string; path: string }>
}
