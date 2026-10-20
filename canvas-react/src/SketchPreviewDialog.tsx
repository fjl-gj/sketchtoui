import { useEffect, useRef, useState } from 'react'
import { Add, Close, PanToolAltOutlined, Remove, ZoomOutMapRounded } from '@mui/icons-material'
import { Alert, Box, Dialog, DialogContent, IconButton, Paper, Stack, Tooltip, Typography } from '@mui/material'

type SketchPreviewDialogProps = {
  open: boolean
  imageUrl: string | null
  onClose: () => void
}

type Point = { x: number; y: number }

const minScale = 0.25
const maxScale = 5

export function SketchPreviewDialog({ open, imageUrl, onClose }: SketchPreviewDialogProps) {
  const dragStartRef = useRef<{ pointer: Point; pan: Point } | null>(null)
  const [scale, setScale] = useState(1)
  const [pan, setPan] = useState<Point>({ x: 0, y: 0 })
  const [loadError, setLoadError] = useState(false)

  useEffect(() => {
    if (!open) return
    setScale(1)
    setPan({ x: 0, y: 0 })
    setLoadError(false)
  }, [open, imageUrl])

  const zoom = (factor: number) => setScale((current) => Math.max(minScale, Math.min(maxScale, current * factor)))
  const reset = () => {
    setScale(1)
    setPan({ x: 0, y: 0 })
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth={false} slotProps={{ paper: { sx: { width: 'min(1440px, 96vw)', height: 'min(940px, 92vh)', overflow: 'hidden' } } }}>
      <Stack direction="row" sx={{ minHeight: 48, px: 1.5, alignItems: 'center', borderBottom: '1px solid #e5eaf1' }}>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 750 }}>原始 Sketch 预览</Typography>
          <Typography variant="caption" color="text.secondary">用于与解析画布进行视觉对照；PNG 本身不包含图层 UUID，因此不替代可选择的图层数据。</Typography>
        </Box>
        <Paper variant="outlined" sx={{ display: 'flex', alignItems: 'center', gap: 0.15, mr: 0.75, p: 0.2, bgcolor: '#f8fafc' }}>
          <Tooltip title="缩小"><IconButton size="small" onClick={() => zoom(1 / 1.2)}><Remove fontSize="small" /></IconButton></Tooltip>
          <Typography variant="caption" sx={{ minWidth: 44, textAlign: 'center', color: 'text.secondary' }}>{Math.round(scale * 100)}%</Typography>
          <Tooltip title="放大"><IconButton size="small" onClick={() => zoom(1.2)}><Add fontSize="small" /></IconButton></Tooltip>
          <Tooltip title="重置缩放与位置"><IconButton size="small" onClick={reset}><ZoomOutMapRounded fontSize="small" /></IconButton></Tooltip>
        </Paper>
        <IconButton size="small" onClick={onClose}><Close fontSize="small" /></IconButton>
      </Stack>
      <DialogContent sx={{ p: 0, position: 'relative', bgcolor: '#edf1f5', overflow: 'hidden' }}>
        {loadError || !imageUrl ? (
          <Stack sx={{ height: '100%', px: 3, alignItems: 'center', justifyContent: 'center' }}>
            <Alert severity="info">这个 Sketch 文件没有可用的 `previews/preview.png`。图层仍可从解析画布中查看。</Alert>
          </Stack>
        ) : (
          <Box
            onWheel={(event) => {
              event.preventDefault()
              zoom(event.deltaY > 0 ? 1 / 1.12 : 1.12)
            }}
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId)
              dragStartRef.current = { pointer: { x: event.clientX, y: event.clientY }, pan }
            }}
            onPointerMove={(event) => {
              const dragStart = dragStartRef.current
              if (!dragStart) return
              setPan({ x: dragStart.pan.x + event.clientX - dragStart.pointer.x, y: dragStart.pan.y + event.clientY - dragStart.pointer.y })
            }}
            onPointerUp={() => { dragStartRef.current = null }}
            onPointerCancel={() => { dragStartRef.current = null }}
            sx={{ width: '100%', height: '100%', display: 'grid', placeItems: 'center', overflow: 'hidden', touchAction: 'none', cursor: 'grab' }}
          >
            <Box component="img" src={imageUrl} alt="原始 Sketch 预览" draggable={false} onError={() => setLoadError(true)} sx={{ maxWidth: '92%', maxHeight: '88%', objectFit: 'contain', userSelect: 'none', transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`, transformOrigin: 'center', boxShadow: '0 12px 28px rgba(15, 23, 42, .16)' }} />
            <Paper variant="outlined" sx={{ position: 'absolute', left: 14, bottom: 14, px: 1, py: 0.55, display: 'flex', alignItems: 'center', gap: 0.55, bgcolor: 'rgba(255,255,255,.9)' }}>
              <PanToolAltOutlined sx={{ fontSize: 15, color: 'text.secondary' }} />
              <Typography variant="caption" color="text.secondary">滚轮缩放，拖拽移动</Typography>
            </Paper>
          </Box>
        )}
      </DialogContent>
    </Dialog>
  )
}
