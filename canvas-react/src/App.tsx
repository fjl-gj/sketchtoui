import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  AppBar,
  Box,
  Button,
  CircularProgress,
  Chip,
  CssBaseline,
  Divider,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  LinearProgress,
  Paper,
  Stack,
  TextField,
  ThemeProvider,
  Toolbar,
  Tooltip,
  Typography,
  createTheme,
} from '@mui/material'
import {
  AccountTreeOutlined,
  Add,
  ApiRounded,
  ChevronRight,
  Close,
  CodeRounded,
  ContentCopyRounded,
  ExpandMore,
  FolderOpenOutlined,
  FolderOutlined,
  DesktopWindowsOutlined,
  ExtensionRounded,
  ImageOutlined,
  MenuRounded,
  PhoneIphoneOutlined,
  Remove,
  TextFieldsOutlined,
  ToggleOffRounded,
  ToggleOnRounded,
  TuneRounded,
  UploadFileRounded,
  ViewCompactOutlined,
  ZoomOutMapRounded,
} from '@mui/icons-material'
import type { CanvasStageHandle } from './CanvasStage'
import { ProjectManager, type ManagedProject } from './ProjectManager'
import { SketchPreviewDialog } from './SketchPreviewDialog'
import type { CanvasData, CanvasManifest, CanvasManifestEntry, LayerNode } from './types'

const appBarHeight = 50
const leftWidth = 276
const rightWidth = 330
const emptyLayerNodes: LayerNode[] = []
const CanvasStage = lazy(() => import('./CanvasStage').then(({ CanvasStage: Stage }) => ({ default: Stage })))

type Project = ManagedProject

type User = {
  id: string
  email: string
  username: string
  phone?: string | null
  emailVerified: boolean
  emailVerifiedAt?: string | null
  status?: string
  lastLoginAt?: string | null
  createdAt: string
}

type ImportJob = {
  id: string
  stage: 'queued' | 'extracting' | 'parsing' | 'complete' | 'failed'
  progress: number
  message: string
  project?: Project
  error?: string
}

type ProjectVersion = {
  id: string
  versionNumber: number
  filename: string
  status: 'pending' | 'processing' | 'ready' | 'failed'
  sourceBytes: number
  totalBytes: number
  groupCount: number
  artboardCount: number
  layerCount: number
  createdAt: string
  completedAt?: string | null
  error?: string | null
  isCurrent: boolean
}

type McpToken = {
  id: string
  name: string
  tokenPrefix: string
  scopes: string[]
  createdAt: string
  enabled: boolean
  lastUsedAt?: string | null
  expiresAt?: string | null
}

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#2f80ed' },
    background: { default: '#edf1f5', paper: '#ffffff' },
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif',
    button: { textTransform: 'none', fontWeight: 600 },
  },
  components: {
    MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
    MuiDrawer: { styleOverrides: { paper: { borderColor: '#e5eaf1' } } },
  },
})

function formatDateTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { dateStyle: 'medium', timeStyle: 'short' })
}

function formatBytes(value: number) {
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  return `${(value / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`
}

function versionStatusLabel(status: ProjectVersion['status']) {
  return { pending: '排队中', processing: '解析中', ready: '已完成', failed: '失败' }[status]
}

function layerIcon(type: string) {
  if (type === 'text') return <TextFieldsOutlined fontSize="small" />
  if (type === 'image') return <ImageOutlined fontSize="small" />
  if (['design_page', 'group', 'shape_group'].includes(type)) return <FolderOutlined fontSize="small" />
  return <ViewCompactOutlined fontSize="small" />
}

type VisibleLayerRow = { node: LayerNode; depth: number; hasChildren: boolean }

function visibleLayerRows(nodes: LayerNode[], expanded: Set<string>) {
  const rows: VisibleLayerRow[] = []
  const visit = (node: LayerNode, depth: number) => {
    const hasChildren = Boolean(node.children?.length)
    rows.push({ node, depth, hasChildren })
    if (hasChildren && expanded.has(node.id)) node.children?.forEach((child) => visit(child, depth + 1))
  }
  nodes.forEach((node) => visit(node, 0))
  return rows
}

type CanvasPlatform = 'desktop' | 'mobile' | 'plugin'

function groupPlatform(group: CanvasManifestEntry): CanvasPlatform {
  const legacyName = group.name.replace(/\s·\s(?:电脑端|移动端（H5）)$/, '').replace(/\s+/g, '')
  if (legacyName === '插件' || legacyName === '插件版') return 'plugin'
  if (group.platform) return group.platform
  return /^\s*h5/i.test(group.name) ? 'mobile' : 'desktop'
}

function platformLabel(platform: CanvasPlatform) {
  return platform === 'mobile' ? '移动端（H5）' : platform === 'plugin' ? '插件版' : '电脑端'
}

function designPageForNode(designPages: LayerNode[], nodeId: string) {
  const contains = (node: LayerNode): boolean => node.id === nodeId || Boolean(node.children?.some(contains))
  return designPages.find(contains) ?? null
}

function hasSameCanvasFrame(first: LayerNode, second: LayerNode) {
  const firstFrame = first.visualFrame ?? first.frame
  const secondFrame = second.visualFrame ?? second.frame
  return Math.abs(firstFrame.absoluteX - secondFrame.absoluteX) < 0.5
    && Math.abs(firstFrame.absoluteY - secondFrame.absoluteY) < 0.5
    && Math.abs(firstFrame.width - secondFrame.width) < 0.5
    && Math.abs(firstFrame.height - secondFrame.height) < 0.5
}

function VirtualLayerTree({ nodes, selected, onSelect }: { nodes: LayerNode[]; selected: LayerNode | null; onSelect: (node: LayerNode) => void }) {
  const rowHeight = 42
  const overscan = 8
  const containerRef = useRef<HTMLDivElement>(null)
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(nodes.map((node) => node.id)))
  const [scrollTop, setScrollTop] = useState(0)
  const [height, setHeight] = useState(0)
  const rows = useMemo(() => visibleLayerRows(nodes, expanded), [nodes, expanded])
  const startIndex = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan)
  const endIndex = Math.min(rows.length, Math.ceil((scrollTop + height) / rowHeight) + overscan)
  const renderedRows = rows.slice(startIndex, endIndex)

  useEffect(() => {
    setExpanded(new Set(nodes.map((node) => node.id)))
    setScrollTop(0)
  }, [nodes])

  useEffect(() => {
    const element = containerRef.current
    if (!element) return undefined
    const observer = new ResizeObserver(() => setHeight(element.clientHeight))
    observer.observe(element)
    setHeight(element.clientHeight)
    return () => observer.disconnect()
  }, [])

  return (
    <Box ref={containerRef} onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)} sx={{ flex: 1, minHeight: 0, overflow: 'auto', px: 1, pb: 2 }}>
      <Box sx={{ position: 'relative', height: rows.length * rowHeight }}>
        <Box sx={{ position: 'absolute', top: startIndex * rowHeight, left: 0, right: 0 }}>
          {renderedRows.map(({ node, depth, hasChildren }) => {
            const isSelected = selected?.id === node.id
            return <ListItemButton key={node.id} selected={isSelected} onClick={() => { onSelect(node); if (hasChildren) setExpanded((current) => { const next = new Set(current); if (next.has(node.id)) next.delete(node.id); else next.add(node.id); return next }) }} sx={{ height: rowHeight - 2, minHeight: rowHeight - 2, borderRadius: 1.4, pl: 1 + depth * 1.5, pr: 1, mb: 0.25 }}>
              <ListItemIcon sx={{ minWidth: 28, color: isSelected ? 'primary.main' : 'text.secondary' }}>{hasChildren ? (expanded.has(node.id) ? <ExpandMore fontSize="small" /> : <ChevronRight fontSize="small" />) : layerIcon(node.type)}</ListItemIcon>
              <Box sx={{ minWidth: 0, flex: 1 }}><Typography noWrap sx={{ fontSize: 13, fontWeight: isSelected ? 700 : 500 }}>{node.name || '未命名图层'}</Typography><Typography noWrap sx={{ fontSize: 10, color: 'text.secondary', textTransform: 'uppercase', letterSpacing: '.03em' }}>{node.type}</Typography></Box>
            </ListItemButton>
          })}
        </Box>
      </Box>
    </Box>
  )
}

function Inspector({ node }: { node: LayerNode | null }) {
  if (!node) {
    return <Box sx={{ p: 3, color: 'text.secondary' }}><Typography variant="body2">从左侧目录或画布中选择一个图层，查看其自身属性。</Typography></Box>
  }
  const { children: _children, ...ownData } = node
  const rows = [
    ['名称', node.name || '未命名图层'],
    ['类型', node.type],
    ['Sketch 类型', node.sketchClass || '—'],
    ['对象 ID', node.id],
    ['X / Y', `${(node.visualFrame ?? node.frame).absoluteX} / ${(node.visualFrame ?? node.frame).absoluteY}`],
    ['宽 / 高', `${(node.visualFrame ?? node.frame).width} / ${(node.visualFrame ?? node.frame).height}`],
    ['不透明度', node.style?.opacity ?? 1],
  ]
  return (
    <Box sx={{ p: 2 }}>
      <Stack spacing={1.25}>
        <Paper variant="outlined" sx={{ p: 1.5, bgcolor: '#f8fafc' }}>
          <Typography variant="overline" color="text.secondary" sx={{ lineHeight: 1 }}>当前图层</Typography>
          <Typography variant="subtitle1" noWrap sx={{ fontWeight: 700 }}>{node.name || '未命名图层'}</Typography>
          <Chip size="small" label={node.type} sx={{ mt: 0.75, fontFamily: 'monospace' }} />
        </Paper>
        <Box component="dl" sx={{ m: 0, display: 'grid', gridTemplateColumns: '82px 1fr', gap: 1, alignItems: 'center' }}>
          {rows.map(([label, value]) => (
            <Box key={String(label)} component="div" sx={{ display: 'contents' }}>
              <Typography component="dt" variant="caption" color="text.secondary">{label}</Typography>
              <Typography component="dd" variant="body2" sx={{ m: 0, p: 0.75, borderRadius: 1, bgcolor: '#f4f6f8', overflowWrap: 'anywhere' }}>{String(value)}</Typography>
            </Box>
          ))}
        </Box>
        <Divider />
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}><CodeRounded fontSize="small" color="primary" /><Typography variant="subtitle2">当前图层 JSON</Typography></Stack>
        <Paper component="pre" variant="outlined" sx={{ m: 0, p: 1.25, maxHeight: 360, overflow: 'auto', bgcolor: '#f7f9fc', color: '#304b70', fontSize: 11, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
          {JSON.stringify(ownData, null, 2)}
        </Paper>
      </Stack>
    </Box>
  )
}

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [project, setProject] = useState<Project | null>(null)
  const [manifest, setManifest] = useState<CanvasManifest | null>(null)
  const [entry, setEntry] = useState<CanvasManifestEntry | null>(null)
  const [data, setData] = useState<CanvasData | null>(null)
  const [selected, setSelected] = useState<LayerNode | null>(null)
  const [hover, setHover] = useState<{ node: LayerNode; x: number; y: number } | null>(null)
  const [leftOpen, setLeftOpen] = useState(true)
  const [rightOpen, setRightOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [workspaceView, setWorkspaceView] = useState<'canvas' | 'projects'>('projects')
  const [projectDialogOpen, setProjectDialogOpen] = useState(false)
  const [reimportProject, setReimportProject] = useState<Project | null>(null)
  const [versionDialogProject, setVersionDialogProject] = useState<Project | null>(null)
  const [projectVersions, setProjectVersions] = useState<ProjectVersion[]>([])
  const [loadingVersions, setLoadingVersions] = useState(false)
  const [projectName, setProjectName] = useState('')
  const [importFile, setImportFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [importProgress, setImportProgress] = useState<{ percent: number; message: string } | null>(null)
  const [zoomPercent, setZoomPercent] = useState(100)
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())
  const [groupPages, setGroupPages] = useState<Record<string, LayerNode[]>>({})
  const [loadingGroupIds, setLoadingGroupIds] = useState<Set<string>>(new Set())
  const [pendingArtboardId, setPendingArtboardId] = useState<string | null>(null)
  const [activeArtboardId, setActiveArtboardId] = useState<string | null>(null)
  const [mcpDialogOpen, setMcpDialogOpen] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [mcpTokens, setMcpTokens] = useState<McpToken[]>([])
  const [mcpUrl, setMcpUrl] = useState('')
  const [mcpTokenName, setMcpTokenName] = useState('Codex Remote MCP')
  const [newMcpToken, setNewMcpToken] = useState<string | null>(null)
  const [mcpLoading, setMcpLoading] = useState(false)
  const stageRef = useRef<CanvasStageHandle>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    void fetch('/api/auth/me')
      .then(async (response) => {
        if (response.status === 401) return null
        const result = await response.json() as { user?: User; error?: string }
        if (!response.ok || !result.user) throw new Error(result.error || '无法读取登录状态')
        return result.user
      })
      .then(setUser)
      .catch((reason: Error) => setError(reason.message))
  }, [])

  useEffect(() => {
    setProjects([])
    setProject(null)
    if (!user?.emailVerified) return
    fetch('/api/projects')
      .then(async (response) => {
        const result = await response.json() as { projects?: Project[]; error?: string }
        if (!response.ok || !result.projects) throw new Error(result.error || '无法读取项目列表')
        return result.projects
      })
      .then((nextProjects) => {
        setProjects(nextProjects)
        setProject(null)
        setWorkspaceView('projects')
      })
      .catch((reason: Error) => setError(reason.message))
  }, [user?.id, user?.emailVerified])

  useEffect(() => {
    setManifest(null)
    setEntry(null)
    setData(null)
    setGroupPages({})
    setExpandedGroups(new Set())
    setPendingArtboardId(null)
    setActiveArtboardId(null)
    if (!project) return
    fetch(`/api/projects/${project.id}/manifest`)
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(`无法读取 ${project.name} 的画布清单`)))
      .then((nextManifest: CanvasManifest) => {
        setManifest(nextManifest)
        const initialEntry = nextManifest.groups.find((group) => group.artboardCount > 0) ?? nextManifest.groups[0] ?? null
        setEntry(initialEntry)
        if (initialEntry) setExpandedGroups(new Set([initialEntry.id]))
        if (!initialEntry) setError(`${project.name} 未解析到任何页面分组`)
      })
      .catch((reason: Error) => setError(reason.message))
  }, [project])

  useEffect(() => {
    if (!entry || !project) return
    const controller = new AbortController()
    setData(null)
    setSelected(null)
    setRightOpen(false)
    fetch(`/api/projects/${project.id}/canvas/${encodeURIComponent(entry.directory)}/canvas.json`, { signal: controller.signal })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(`无法读取 ${entry.name} 数据`)))
      .then((nextData: CanvasData) => {
        if (controller.signal.aborted) return
        const canvasData = { ...nextData, imageBaseUrl: `/api/projects/${project.id}/assets` }
        const requestedArtboard = pendingArtboardId ? canvasData.designPages.find((node) => node.id === pendingArtboardId) : null
        setGroupPages((current) => ({ ...current, [entry.id]: canvasData.designPages }))
        setActiveArtboardId((current) => requestedArtboard?.id ?? (canvasData.designPages.some((node) => node.id === current) ? current : canvasData.designPages[0]?.id ?? null))
        setData(canvasData)
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setError(reason.message)
      })
    return () => controller.abort()
  }, [entry, project])

  useEffect(() => {
    if (!data || !pendingArtboardId) return
    const artboard = data.designPages.find((node) => node.id === pendingArtboardId)
    if (!artboard) return
    setActiveArtboardId(artboard.id)
    setSelected(artboard)
    setRightOpen(true)
    setPendingArtboardId(null)
  }, [data, pendingArtboardId])

  const openImportDialog = (targetProject: Project | null = null) => {
    setReimportProject(targetProject)
    setProjectName(targetProject ? targetProject.name : '')
    setImportFile(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
    setProjectDialogOpen(true)
  }

  const openVersionDialog = async (targetProject: Project) => {
    setVersionDialogProject(targetProject)
    setProjectVersions([])
    setLoadingVersions(true)
    try {
      const response = await fetch(`/api/projects/${targetProject.id}/versions`)
      const result = await response.json() as { versions?: ProjectVersion[]; error?: string }
      if (!response.ok || !result.versions) throw new Error(result.error || '无法读取项目版本')
      setProjectVersions(result.versions)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法读取项目版本')
    } finally {
      setLoadingVersions(false)
    }
  }

  const importProject = async () => {
    if (!importFile) {
      setError('请选择要导入的 .sketch 文件')
      return
    }
    setUploading(true)
    setError(null)
    setImportProgress({ percent: 0, message: '正在上传 Sketch 文件' })
    try {
      const initialJob = await new Promise<ImportJob>((resolve, reject) => {
        const request = new XMLHttpRequest()
        request.open('POST', reimportProject ? `/api/projects/${reimportProject.id}/versions` : '/api/projects')
        request.responseType = 'json'
        request.setRequestHeader('Content-Type', 'application/octet-stream')
        request.setRequestHeader('X-Filename', encodeURIComponent(importFile.name))
        if (!reimportProject) request.setRequestHeader('X-Project-Name', encodeURIComponent(projectName.trim() || importFile.name.replace(/\.sketch$/i, '')))
        request.upload.onprogress = (event) => {
          if (event.lengthComputable) setImportProgress({ percent: Math.round(event.loaded / event.total * 15), message: '正在上传 Sketch 文件' })
        }
        request.onerror = () => reject(new Error('上传失败，请检查网络或服务状态'))
        request.onload = () => {
          const result = request.response as { import?: ImportJob; error?: string } | null
          if (request.status < 200 || request.status >= 300 || !result?.import) reject(new Error(result?.error || '创建导入任务失败'))
          else resolve(result.import)
        }
        request.send(importFile)
      })
      let job = initialJob
      while (job.stage !== 'complete') {
        if (job.stage === 'failed') throw new Error(job.error || job.message || '解析失败')
        setImportProgress({ percent: Math.max(15, job.progress), message: job.message })
        await new Promise((resolve) => window.setTimeout(resolve, 500))
        const response = await fetch(`/api/imports/${job.id}`)
        const result = await response.json() as { import?: ImportJob; error?: string }
        if (!response.ok || !result.import) throw new Error(result.error || '无法读取导入进度')
        job = result.import
      }
      if (!job.project) throw new Error('导入完成但未返回项目数据')
      setImportProgress({ percent: 100, message: job.message })
      setProjects((items) => items.some((item) => item.id === job.project!.id)
        ? items.map((item) => item.id === job.project!.id ? job.project! : item)
        : [job.project!, ...items])
      setProject(job.project)
      setWorkspaceView('canvas')
      setProjectDialogOpen(false)
      setNotice('导入与解析完成')
      setProjectName('')
      setImportFile(null)
      setReimportProject(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '导入失败')
    } finally {
      setUploading(false)
      window.setTimeout(() => setImportProgress(null), 450)
    }
  }

  const logout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' })
    window.location.reload()
  }

  const deleteProject = async (item: Project) => {
    const response = await fetch(`/api/projects/${item.id}`, { method: 'DELETE' })
    const result = await response.json() as { error?: string }
    if (!response.ok) throw new Error(result.error || '删除项目失败')
    const remaining = projects.filter((projectItem) => projectItem.id !== item.id)
    setProjects(remaining)
    if (project?.id === item.id) setProject(remaining[0] ?? null)
    setNotice(`已删除项目：${item.name}`)
  }

  const loadMcpTokens = async () => {
    const [tokensResponse, configResponse] = await Promise.all([fetch('/api/mcp/tokens'), fetch('/api/mcp/config')])
    const tokensResult = await tokensResponse.json() as { tokens?: McpToken[]; error?: string }
    const configResult = await configResponse.json() as { url?: string; error?: string }
    if (!tokensResponse.ok) throw new Error(tokensResult.error || '无法读取 MCP Token')
    if (!configResponse.ok) throw new Error(configResult.error || '无法读取 MCP 服务地址')
    setMcpTokens(tokensResult.tokens ?? [])
    setMcpUrl(configResult.url ?? '')
  }

  const openMcpDialog = () => {
    setNewMcpToken(null)
    setMcpDialogOpen(true)
    void loadMcpTokens().catch((reason: Error) => setError(reason.message))
  }

  const createMcpToken = async () => {
    setMcpLoading(true)
    try {
      const response = await fetch('/api/mcp/tokens', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: mcpTokenName }) })
      const result = await response.json() as { token?: McpToken; value?: string; error?: string }
      if (!response.ok || !result.value) throw new Error(result.error || '创建 MCP Token 失败')
      setNewMcpToken(result.value)
      setMcpTokens((current) => result.token ? [result.token, ...current] : current)
      setNotice('MCP Token 已生成，请立即复制并妥善保存')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '创建 MCP Token 失败')
    } finally {
      setMcpLoading(false)
    }
  }

  const setMcpTokenEnabled = async (token: McpToken, enabled: boolean) => {
    const action = enabled ? '启用' : '禁用'
    if (!window.confirm(`确认${action} MCP Token“${token.name}”？${enabled ? '已配置该 Token 的 Codex 将恢复访问。' : '已配置该 Token 的 Codex 将立即无法访问。'}`)) return
    setMcpLoading(true)
    try {
      const response = await fetch(`/api/mcp/tokens/${token.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) })
      const result = await response.json() as { token?: McpToken; error?: string }
      if (!response.ok || !result.token) throw new Error(result.error || `${action} MCP Token 失败`)
      setMcpTokens((current) => current.map((item) => item.id === token.id ? result.token as McpToken : item))
      setNotice(`MCP Token 已${action}：${token.name}`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `${action} MCP Token 失败`)
    } finally {
      setMcpLoading(false)
    }
  }

  const copyText = async (value: string, message: string) => {
    try {
      const fallbackCopy = () => {
        const textArea = document.createElement('textarea')
        textArea.value = value
        textArea.setAttribute('readonly', '')
        textArea.style.position = 'fixed'
        textArea.style.opacity = '0'
        textArea.style.pointerEvents = 'none'
        document.body.append(textArea)
        textArea.select()
        try {
          if (!document.execCommand('copy')) throw new Error('Clipboard fallback failed')
        } finally {
          textArea.remove()
        }
      }
      if (window.isSecureContext && navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(value)
        } catch {
          fallbackCopy()
        }
      } else {
        fallbackCopy()
      }
      setNotice(message)
    } catch {
      setError('复制失败，请使用 HTTPS 页面或检查浏览器剪贴板权限')
    }
  }

  const selectNode = (node: LayerNode | null, focus = true) => {
    const designPage = node && data ? designPageForNode(data.designPages, node.id) : null
    const selectedNode = node && designPage && node.type === 'rectangle' && hasSameCanvasFrame(node, designPage) ? designPage : node
    setSelected(selectedNode)
    if (!selectedNode) return
    if (designPage) setActiveArtboardId(designPage.id)
    setRightOpen(true)
    if (focus) window.setTimeout(() => stageRef.current?.focus(selectedNode), 0)
  }

  const mainMarginLeft = workspaceView === 'canvas' && leftOpen ? `${leftWidth}px` : 0
  const mainMarginRight = workspaceView === 'canvas' && rightOpen ? `${rightWidth}px` : 0
  const groups = (manifest?.groups ?? []).filter((group) => group.artboardCount > 0)
  const desktopGroups = groups.filter((group) => groupPlatform(group) === 'desktop')
  const mobileGroups = groups.filter((group) => groupPlatform(group) === 'mobile')
  const pluginGroups = groups.filter((group) => groupPlatform(group) === 'plugin')
  const activeArtboard = data?.designPages.find((node) => node.id === activeArtboardId) ?? null
  const layerTreeNodes = useMemo(() => activeArtboard ? [activeArtboard] : emptyLayerNodes, [activeArtboard])

  const copyMcpArtboardLink = () => {
    if (!project || !entry || !activeArtboard) return
    const resource = `sketchtoui://projects/${encodeURIComponent(project.id)}/groups/${encodeURIComponent(entry.id)}/artboards/${encodeURIComponent(activeArtboard.id)}`
    void copyText(resource, '已复制当前设计页面的 MCP 链接')
  }

  const groupLabel = (group: CanvasManifestEntry) => group.name.replace(/\s·\s(?:电脑端|移动端（H5）)$/, '')
  const originalPreviewPath = manifest?.previews?.[0]?.path ?? 'previews/preview.png'
  const originalPreviewUrl = project ? `/api/projects/${project.id}/assets/${originalPreviewPath.split('/').map(encodeURIComponent).join('/')}` : null

  const loadGroupPages = async (group: CanvasManifestEntry) => {
    if (!project || groupPages[group.id] || loadingGroupIds.has(group.id)) return
    setLoadingGroupIds((current) => new Set(current).add(group.id))
    try {
      const response = await fetch(`/api/projects/${project.id}/canvas/${encodeURIComponent(group.directory)}/canvas.json`)
      if (!response.ok) throw new Error(`无法读取 ${groupLabel(group)} 的设计页面`)
      const canvasData = await response.json() as CanvasData
      setGroupPages((current) => ({ ...current, [group.id]: canvasData.designPages }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法读取设计页面')
    } finally {
      setLoadingGroupIds((current) => {
        const next = new Set(current)
        next.delete(group.id)
        return next
      })
    }
  }

  const toggleGroup = (group: CanvasManifestEntry) => {
    const isExpanded = expandedGroups.has(group.id)
    setExpandedGroups((current) => {
      const next = new Set(current)
      if (isExpanded) next.delete(group.id)
      else next.add(group.id)
      return next
    })
    if (!isExpanded) void loadGroupPages(group)
  }

  const selectArtboard = (group: CanvasManifestEntry, artboard: LayerNode) => {
    if (entry?.id === group.id && data) {
      setActiveArtboardId(artboard.id)
      selectNode(artboard)
      return
    }
    setEntry(group)
    setPendingArtboardId(artboard.id)
  }

  const renderGroup = (group: CanvasManifestEntry) => {
    const isExpanded = expandedGroups.has(group.id)
    const pages = groupPages[group.id] ?? []
    const isLoading = loadingGroupIds.has(group.id)
    return (
      <Box key={group.id} sx={{ mb: 0.2 }}>
        <ListItemButton selected={entry?.id === group.id} onClick={() => { setEntry(group); if (!isExpanded) toggleGroup(group) }} sx={{ borderRadius: 1.5, minHeight: 34, pr: 0.4 }}>
          <ListItemIcon sx={{ minWidth: 28 }}>{entry?.id === group.id ? <FolderOpenOutlined color="primary" fontSize="small" /> : <FolderOutlined fontSize="small" />}</ListItemIcon>
          <Typography sx={{ flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: entry?.id === group.id ? 700 : 500 }} noWrap>{groupLabel(group)}</Typography>
          <Chip label={`${group.artboardCount} 页`} size="small" sx={{ height: 18, fontSize: 9 }} />
          <IconButton size="small" aria-label={`${isExpanded ? '收起' : '展开'}${groupLabel(group)}`} onClick={(event) => { event.stopPropagation(); toggleGroup(group) }} sx={{ ml: 0.15 }}>
            {isExpanded ? <ExpandMore fontSize="small" /> : <ChevronRight fontSize="small" />}
          </IconButton>
        </ListItemButton>
        {isExpanded && <Box sx={{ ml: 1.65, pl: 0.95, borderLeft: '1px solid #e3eaf3' }}>
          {isLoading && <Box sx={{ minHeight: 28, display: 'flex', alignItems: 'center', gap: 0.75, color: 'text.secondary', px: 0.8 }}><CircularProgress size={13} /><Typography variant="caption">加载设计页面…</Typography></Box>}
          {!isLoading && pages.map((artboard) => <ListItemButton key={artboard.id} selected={selected?.id === artboard.id} onClick={() => selectArtboard(group, artboard)} sx={{ minHeight: 30, borderRadius: 1.2, py: 0.25, pl: 1, pr: 0.8 }}>
            <ListItemIcon sx={{ minWidth: 24, color: selected?.id === artboard.id ? 'primary.main' : 'text.secondary' }}><ViewCompactOutlined sx={{ fontSize: 16 }} /></ListItemIcon>
            <Typography noWrap sx={{ fontSize: 12, fontWeight: selected?.id === artboard.id ? 700 : 500 }}>{artboard.name || '未命名设计页面'}</Typography>
          </ListItemButton>)}
          {!isLoading && pages.length === 0 && <Typography variant="caption" color="text.disabled" sx={{ display: 'block', px: 0.8, py: 0.6 }}>暂无设计页面</Typography>}
        </Box>}
      </Box>
    )
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ width: '100vw', height: '100vh', overflow: 'hidden', bgcolor: 'background.default' }}>
        <AppBar position="fixed" color="inherit" elevation={0} sx={{ zIndex: (themeValue) => themeValue.zIndex.drawer + 1, borderBottom: '1px solid #e5eaf1', bgcolor: 'rgba(255,255,255,.94)', backdropFilter: 'blur(12px)' }}>
          <Toolbar variant="dense" sx={{ minHeight: appBarHeight, gap: 1 }}>
            <Tooltip title="显示或隐藏目录"><IconButton size="small" onClick={() => setLeftOpen((value) => !value)}><MenuRounded fontSize="small" /></IconButton></Tooltip>
            <FolderOpenOutlined color="primary" />
            <Typography variant="subtitle2" sx={{ fontWeight: 750 }}>{entry?.name ?? project?.name ?? 'Sketch Canvas'}</Typography>
            {data && <Typography variant="caption" color="text.secondary">{data.designPages.length} 个设计页面 · {data.statistics.totalLayers} 图层</Typography>}
            <Box sx={{ flexGrow: 1 }} />
            {user && <Typography variant="caption" color="text.secondary">{user.username}</Typography>}
            {user && <Button size="small" onClick={() => void logout()}>退出</Button>}
            <Button size="small" disabled={!user?.emailVerified} startIcon={<ApiRounded fontSize="small" />} onClick={openMcpDialog}>MCP</Button>
            <Button size="small" variant={workspaceView === 'projects' ? 'outlined' : 'text'} disabled={!user?.emailVerified} startIcon={<FolderOpenOutlined />} onClick={() => setWorkspaceView('projects')}>项目</Button>
            {workspaceView === 'projects' && project && <Button size="small" onClick={() => setWorkspaceView('canvas')}>画布</Button>}
            {workspaceView === 'canvas' && project && <Button size="small" startIcon={<ImageOutlined fontSize="small" />} onClick={() => setPreviewOpen(true)}>原始预览</Button>}
            <Button size="small" disabled={!user?.emailVerified} variant="contained" startIcon={<UploadFileRounded fontSize="small" />} onClick={() => openImportDialog()}>导入 Sketch</Button>
            <Paper variant="outlined" sx={{ display: 'flex', alignItems: 'center', gap: 0.25, p: 0.25, bgcolor: '#f8fafc' }}>
              <Tooltip title="缩小（-）"><IconButton size="small" onClick={() => stageRef.current?.zoom(1 / 1.15)}><Remove fontSize="small" /></IconButton></Tooltip>
              <Tooltip title="画布获得焦点后可使用 +、- 缩放，按 0 适应窗口"><Typography variant="caption" sx={{ minWidth: 48, textAlign: 'center', color: 'text.secondary', cursor: 'help' }}>{zoomPercent}%</Typography></Tooltip>
              <Tooltip title="放大（+）"><IconButton size="small" onClick={() => stageRef.current?.zoom(1.15)}><Add fontSize="small" /></IconButton></Tooltip>
              <Tooltip title="适应窗口（0）"><IconButton size="small" onClick={() => stageRef.current?.fit()}><ZoomOutMapRounded fontSize="small" /></IconButton></Tooltip>
            </Paper>
          </Toolbar>
        </AppBar>

        <Drawer variant="persistent" anchor="left" open={workspaceView === 'canvas' && leftOpen} sx={{ '& .MuiDrawer-paper': { top: appBarHeight, width: leftWidth, height: `calc(100% - ${appBarHeight}px)`, boxSizing: 'border-box', display: 'flex', flexDirection: 'column', overflow: 'hidden' } }}>
          <Box sx={{ p: 1.1, pb: 0.7, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}><Typography variant="overline" color="text.secondary">页面分组</Typography>{manifest && <Chip label={`${groups.length} 组`} size="small" sx={{ height: 18, fontSize: 9 }} />}</Box>
          <Box sx={{ px: 0.8, flex: '0 0 45%', minHeight: 280, overflow: 'auto' }}>
            {[{ key: 'desktop', label: '电脑端', icon: <DesktopWindowsOutlined fontSize="small" />, items: desktopGroups }, { key: 'mobile', label: '移动端（H5）', icon: <PhoneIphoneOutlined fontSize="small" />, items: mobileGroups }, { key: 'plugin', label: '插件版', icon: <ExtensionRounded fontSize="small" />, items: pluginGroups }].map((section) => <Box key={section.key} sx={{ mb: 1.25 }}><Box sx={{ px: 0.75, pb: 0.4, display: 'flex', alignItems: 'center', gap: 0.75, color: 'text.secondary' }}>{section.icon}<Typography variant="caption" sx={{ fontWeight: 700 }}>{section.label}</Typography><Typography variant="caption" sx={{ ml: 'auto' }}>{section.items.length}</Typography></Box>{section.items.length > 0 ? <List dense disablePadding>{section.items.map(renderGroup)}</List> : <Typography variant="caption" color="text.disabled" sx={{ display: 'block', px: 0.75, py: 0.5 }}>暂无分组</Typography>}</Box>)}
          </Box>
          <Divider sx={{ my: 1 }} />
          <Box sx={{ px: 1.1, pb: 0.35, display: 'flex', alignItems: 'center', gap: 0.6 }}><AccountTreeOutlined fontSize="small" color="action" /><Typography variant="overline" color="text.secondary">图层目录{activeArtboard ? ` · ${activeArtboard.name || '未命名页面'}` : ''}</Typography></Box>
          <VirtualLayerTree nodes={layerTreeNodes} selected={selected} onSelect={(item) => selectNode(item)} />
        </Drawer>

        <Drawer variant="persistent" anchor="right" open={workspaceView === 'canvas' && rightOpen} sx={{ '& .MuiDrawer-paper': { top: appBarHeight, width: rightWidth, height: `calc(100% - ${appBarHeight}px)`, boxSizing: 'border-box' } }}>
          <Toolbar variant="dense" sx={{ minHeight: 44, px: 1.5, borderBottom: '1px solid #e5eaf1' }}>
            <TuneRounded fontSize="small" color="primary" />
            <Typography variant="subtitle2" sx={{ ml: 1, flexGrow: 1 }}>属性检查器</Typography>
            <IconButton size="small" onClick={() => setRightOpen(false)}><Close fontSize="small" /></IconButton>
          </Toolbar>
          <Box sx={{ flex: 1, overflow: 'auto' }}><Inspector node={selected} /></Box>
        </Drawer>

        <Box component="main" sx={{ position: 'fixed', top: appBarHeight, bottom: 0, left: 0, right: 0, ml: mainMarginLeft, mr: mainMarginRight, transition: 'margin .22s cubic-bezier(.2,.8,.2,1)' }}>
          {workspaceView === 'projects' ? <ProjectManager projects={projects} activeProjectId={project?.id} onOpen={(item) => { setProject(item); setWorkspaceView('canvas') }} onDelete={deleteProject} onImport={() => openImportDialog()} onReimport={(item) => openImportDialog(item)} onVersions={(item) => void openVersionDialog(item)} /> : <>
          {error && <Alert severity="error" sx={{ position: 'absolute', zIndex: 4, top: 20, left: 20 }}>{error}</Alert>}
          {notice && <Alert severity="success" onClose={() => setNotice(null)} sx={{ position: 'absolute', zIndex: 4, top: 20, left: 20 }}>{notice}</Alert>}
          {data && <Paper variant="outlined" sx={{ position: 'absolute', zIndex: 3, top: 12, right: 12, px: 1, py: 0.6, bgcolor: 'rgba(255,255,255,.94)', backdropFilter: 'blur(8px)' }}><Typography variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>当前画布 · {platformLabel(groupPlatform(entry ?? { ...data.sketchPage, directory: '', artboardCount: 0, layerCount: 0 }))}</Typography><Typography variant="body2" sx={{ fontWeight: 700 }}>{entry?.name ?? data.sketchPage.name}</Typography><Typography variant="caption" color="text.secondary">{data.designPages.length} 个设计页面 · {data.statistics.totalLayers} 个图层</Typography>{activeArtboard && <Button size="small" startIcon={<ContentCopyRounded sx={{ fontSize: 14 }} />} onClick={copyMcpArtboardLink} sx={{ mt: 0.35, px: 0, minWidth: 0, fontSize: 11 }}>复制 {activeArtboard.name || '当前页面'} MCP 链接</Button>}</Paper>}
          {data ? data.designPages.length > 0 ? <Suspense fallback={<Stack sx={{ height: '100%', color: 'text.secondary', alignItems: 'center', justifyContent: 'center' }}><Typography>正在加载画布渲染器…</Typography></Stack>}><CanvasStage ref={stageRef} data={data} initialFocus={activeArtboard} selected={selected} onSelect={(node) => selectNode(node, false)} onHover={(node, position) => setHover(node && position ? { node, ...position } : null)} onViewportChange={(scale) => setZoomPercent(Math.round(scale * 100))} /></Suspense> : <Stack sx={{ height: '100%', color: 'text.secondary', alignItems: 'center', justifyContent: 'center', gap: 1 }}><Typography variant="h6">该分组没有可展示的设计页面</Typography><Typography variant="body2">请从左侧选择一个含画板的分组查看画布。</Typography></Stack> : <Stack sx={{ height: '100%', color: 'text.secondary', alignItems: 'center', justifyContent: 'center', gap: 1.5 }}>{!user ? <><Typography variant="h6">登录状态已失效</Typography><Button variant="contained" onClick={() => window.location.reload()}>重新登录</Button></> : <><Typography>{project ? '正在加载画布数据…' : '选择或导入一个 Sketch 项目后即可开始查看。'}</Typography>{!project && <Button variant="contained" startIcon={<UploadFileRounded />} onClick={() => setProjectDialogOpen(true)}>导入 .sketch 文件</Button>}</>}</Stack>}
          </>}
        </Box>

        {hover && (
          <Paper elevation={6} sx={{ position: 'fixed', zIndex: (themeValue) => themeValue.zIndex.tooltip, left: hover.x + 14, top: hover.y + 14, px: 1.25, py: 0.9, pointerEvents: 'none', bgcolor: 'rgba(25,38,56,.95)', color: '#fff', maxWidth: 280 }}>
            <Typography variant="overline" sx={{ display: 'block', color: '#9bcbff', lineHeight: 1.2 }}>{hover.node.type}</Typography>
            <Typography variant="body2" noWrap sx={{ fontWeight: 700 }}>{hover.node.name || '未命名图层'}</Typography>
            <Typography variant="caption" sx={{ color: '#d8e6f6' }}>{Math.round((hover.node.visualFrame ?? hover.node.frame).width)} × {Math.round((hover.node.visualFrame ?? hover.node.frame).height)} · x: {Math.round((hover.node.visualFrame ?? hover.node.frame).absoluteX)}, y: {Math.round((hover.node.visualFrame ?? hover.node.frame).absoluteY)}</Typography>
          </Paper>
        )}

        <Dialog open={projectDialogOpen} onClose={() => { if (!uploading) { setProjectDialogOpen(false); setReimportProject(null) } }} fullWidth maxWidth="sm">
          <DialogTitle>{reimportProject ? `重新导入 · ${reimportProject.name}` : '导入 Sketch 项目'}</DialogTitle>
          <DialogContent dividers>
            <Stack spacing={2}>
              <Box><Stack spacing={1.5}>{!reimportProject && <TextField size="small" disabled={uploading} label="项目名称（可选）" value={projectName} onChange={(event) => setProjectName(event.target.value)} />}<Button component="label" disabled={uploading} variant="outlined" startIcon={<UploadFileRounded />}>{importFile ? importFile.name : '选择 .sketch 文件'}<input ref={fileInputRef} hidden type="file" accept=".sketch" onChange={(event) => setImportFile(event.target.files?.[0] ?? null)} /></Button>{importProgress && <Box><Stack direction="row" sx={{ mb: 0.6, justifyContent: 'space-between' }}><Typography variant="caption">{importProgress.message}</Typography><Typography variant="caption" color="text.secondary">{importProgress.percent}%</Typography></Stack><LinearProgress variant="determinate" value={importProgress.percent} /></Box>}<Typography variant="caption" color="text.secondary">{reimportProject ? '新文件会作为一个版本解析；在解析成功前，当前画布和 MCP 仍继续读取旧版本。' : '文件会上传到 MinIO，自动解压并按 `meta.json` 解析为画布数据。'}</Typography></Stack></Box>
            </Stack>
          </DialogContent>
          <DialogActions><Button disabled={uploading} onClick={() => { setProjectDialogOpen(false); setReimportProject(null) }}>关闭</Button><Button variant="contained" disabled={!importFile || uploading} onClick={() => void importProject()}>{uploading ? '正在导入…' : reimportProject ? '创建新版本' : '导入并解析'}</Button></DialogActions>
        </Dialog>

        <Dialog open={Boolean(versionDialogProject)} onClose={() => setVersionDialogProject(null)} fullWidth maxWidth="sm">
          <DialogTitle>版本历史 · {versionDialogProject?.name}</DialogTitle>
          <DialogContent dividers>
            {loadingVersions ? <Box sx={{ minHeight: 180, display: 'grid', placeItems: 'center' }}><CircularProgress size={28} /></Box> : <Stack spacing={1.1}>
              {projectVersions.length === 0 ? <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>暂无版本记录。</Typography> : projectVersions.map((version) => <Paper key={version.id} variant="outlined" sx={{ p: 1.4, borderColor: version.isCurrent ? 'primary.main' : 'divider', bgcolor: version.isCurrent ? 'rgba(47,128,237,.035)' : 'background.paper' }}>
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.65 }}><Typography variant="subtitle2" sx={{ fontWeight: 760, flex: 1 }}>v{version.versionNumber}</Typography>{version.isCurrent && <Chip label="当前使用" size="small" color="primary" sx={{ height: 22 }} />}<Chip label={versionStatusLabel(version.status)} size="small" color={version.status === 'failed' ? 'error' : version.status === 'ready' ? 'success' : 'default'} variant={version.status === 'ready' ? 'filled' : 'outlined'} sx={{ height: 22 }} /></Stack>
                <Typography variant="body2" noWrap>{version.filename}</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.45 }}>创建于 {formatDateTime(version.createdAt)} · {version.completedAt ? `完成于 ${formatDateTime(version.completedAt)}` : '尚未完成'}</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>{version.groupCount} 个分组 · {version.artboardCount} 个页面 · {version.layerCount} 个图层 · {formatBytes(version.totalBytes || version.sourceBytes)}</Typography>
                {version.error && <Alert severity="error" sx={{ mt: 1, py: 0, '& .MuiAlert-message': { py: 0.35, wordBreak: 'break-word' } }}>{version.error}</Alert>}
              </Paper>)}
            </Stack>}
          </DialogContent>
          <DialogActions><Button onClick={() => setVersionDialogProject(null)}>关闭</Button></DialogActions>
        </Dialog>

        <SketchPreviewDialog open={previewOpen} imageUrl={originalPreviewUrl} onClose={() => setPreviewOpen(false)} />

        <Dialog open={mcpDialogOpen} onClose={() => setMcpDialogOpen(false)} fullWidth maxWidth="sm">
          <DialogTitle>Remote MCP</DialogTitle>
          <DialogContent dividers>
            <Stack spacing={2}>
              <Typography variant="body2" color="text.secondary">创建个人 Token 后，Codex 可通过 Remote MCP 只读访问你的项目、页面、图层和文本布局信息。</Typography>
              <TextField size="small" label="Token 名称" value={mcpTokenName} onChange={(event) => setMcpTokenName(event.target.value)} disabled={mcpLoading} />
              <Button variant="contained" startIcon={<ApiRounded />} onClick={() => void createMcpToken()} disabled={mcpLoading}>{mcpLoading ? '正在创建…' : '创建 MCP Token'}</Button>
              {newMcpToken && <Paper variant="outlined" sx={{ p: 1.5, bgcolor: '#fffaf0', borderColor: '#f2d28d' }}><Typography variant="subtitle2" sx={{ color: '#8a5a00' }}>请立即保存 Token</Typography><Typography variant="caption" sx={{ display: 'block', mt: 0.4, color: 'text.secondary' }}>为安全起见，关闭此窗口后不会再次显示完整 Token。</Typography><Stack direction="row" spacing={1} sx={{ mt: 1, alignItems: 'center' }}><TextField size="small" value={newMcpToken} slotProps={{ input: { readOnly: true } }} sx={{ flex: 1, '& input': { fontFamily: 'monospace', fontSize: 12 } }} /><Tooltip title="复制 Token"><IconButton onClick={() => void copyText(newMcpToken, 'MCP Token 已复制')}><ContentCopyRounded fontSize="small" /></IconButton></Tooltip></Stack></Paper>}
              <Paper variant="outlined" sx={{ p: 1.5, bgcolor: '#f7f9fc' }}><Typography variant="subtitle2">Codex 配置</Typography><Typography component="pre" sx={{ m: 0, mt: 0.8, whiteSpace: 'pre-wrap', fontSize: 12, lineHeight: 1.65, color: '#304b70' }}>{`[mcp_servers.sketchtoui]\nenabled = true\nurl = "${mcpUrl || 'http://127.0.0.1:8124/mcp'}"\nbearer_token_env_var = "SKETCHTOUI_MCP_TOKEN"`}</Typography></Paper>
              <Divider />
              <Typography variant="subtitle2">已创建 Token</Typography>
              {mcpTokens.length === 0 ? <Typography variant="body2" color="text.secondary">还没有 MCP Token。</Typography> : <Stack spacing={0.8}>{mcpTokens.map((token) => <Paper key={token.id} variant="outlined" sx={{ px: 1.25, py: 0.85, opacity: token.enabled ? 1 : 0.68 }}><Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}><Box sx={{ minWidth: 0, flex: 1 }}><Stack direction="row" spacing={0.65} sx={{ alignItems: 'center' }}><Typography variant="body2" noWrap sx={{ fontWeight: 700 }}>{token.name}</Typography><Chip size="small" color={token.enabled ? 'success' : 'default'} label={token.enabled ? '已启用' : '已禁用'} sx={{ height: 20, fontSize: 11 }} /></Stack><Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>{token.tokenPrefix}… · {token.scopes.join(', ')}</Typography></Box><Tooltip title={token.enabled ? '禁用 Token' : '启用 Token'}><IconButton color={token.enabled ? 'warning' : 'success'} size="small" disabled={mcpLoading} onClick={() => void setMcpTokenEnabled(token, !token.enabled)}>{token.enabled ? <ToggleOffRounded fontSize="small" /> : <ToggleOnRounded fontSize="small" />}</IconButton></Tooltip></Stack></Paper>)}</Stack>}
            </Stack>
          </DialogContent>
          <DialogActions><Button onClick={() => setMcpDialogOpen(false)}>关闭</Button></DialogActions>
        </Dialog>

      </Box>
    </ThemeProvider>
  )
}
