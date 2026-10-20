import { DeleteOutlined, FolderOpenOutlined, HistoryOutlined, OpenInNewRounded, PublishedWithChangesOutlined, UploadFileRounded } from '@mui/icons-material'
import { Box, Button, Chip, IconButton, Paper, Stack, Tooltip, Typography } from '@mui/material'

export type ManagedProject = {
  id: string
  name: string
  sourceFilename: string
  createdAt: string
  updatedAt?: string
  groupCount: number
  currentVersionNumber?: number | null
}

type ProjectManagerProps = {
  projects: ManagedProject[]
  activeProjectId?: string
  onOpen: (project: ManagedProject) => void
  onDelete: (project: ManagedProject) => Promise<void>
  onImport: () => void
  onReimport: (project: ManagedProject) => void
  onVersions: (project: ManagedProject) => void
}

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { dateStyle: 'medium', timeStyle: 'short' })
}

export function ProjectManager({ projects, activeProjectId, onOpen, onDelete, onImport, onReimport, onVersions }: ProjectManagerProps) {
  const deleteProject = async (project: ManagedProject) => {
    if (!window.confirm(`确认删除项目“${project.name}”？该操作会同时删除 MinIO 中的 Sketch 文件和解析画布。`)) return
    await onDelete(project)
  }

  return <Box sx={{ height: '100%', overflow: 'auto', bgcolor: '#f5f8fc', p: { xs: 2, md: 4 } }}>
    <Box sx={{ width: 'min(1180px, 100%)', mx: 'auto' }}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3, justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
        <Box><Typography variant="h4" sx={{ fontWeight: 760, letterSpacing: '-.03em' }}>项目管理</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>管理已导入的 Sketch 文件，选择项目后进入画布查看和图层检查。</Typography></Box>
        <Button variant="contained" startIcon={<UploadFileRounded />} onClick={onImport}>导入 Sketch</Button>
      </Stack>

      {projects.length === 0 ? <Paper variant="outlined" sx={{ minHeight: 280, display: 'grid', placeItems: 'center', textAlign: 'center', p: 4 }}><Box><FolderOpenOutlined color="primary" sx={{ fontSize: 42, mb: 1 }} /><Typography variant="h6">还没有导入项目</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, mb: 2 }}>导入 `.sketch` 文件后，系统会自动解析电脑端与 H5 移动端分组。</Typography><Button variant="contained" startIcon={<UploadFileRounded />} onClick={onImport}>导入第一个 Sketch</Button></Box></Paper> : <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 2 }}>
        {projects.map((project) => <Paper key={project.id} variant="outlined" sx={{ p: 2, borderColor: project.id === activeProjectId ? 'primary.main' : 'divider', boxShadow: project.id === activeProjectId ? '0 0 0 3px rgba(47,128,237,.10)' : 'none' }}><Stack direction="row" spacing={1.25} sx={{ alignItems: 'flex-start' }}><Box sx={{ width: 40, height: 40, display: 'grid', placeItems: 'center', borderRadius: 2, color: 'primary.main', bgcolor: 'primary.50' }}><FolderOpenOutlined /></Box><Box sx={{ minWidth: 0, flex: 1 }}><Typography noWrap sx={{ fontWeight: 750 }}>{project.name}</Typography><Typography noWrap variant="caption" color="text.secondary">{project.sourceFilename}</Typography></Box><Tooltip title="删除项目"><IconButton size="small" color="error" onClick={() => void deleteProject(project)}><DeleteOutlined fontSize="small" /></IconButton></Tooltip></Stack><Stack direction="row" spacing={0.75} sx={{ mt: 2, mb: 1.5, flexWrap: 'wrap' }}><Chip label={`${project.groupCount} 个分组`} size="small" />{project.currentVersionNumber && <Chip label={`v${project.currentVersionNumber}`} size="small" color="primary" variant="outlined" />}<Chip label={formatDate(project.updatedAt || project.createdAt)} size="small" variant="outlined" /></Stack><Stack direction="row" spacing={0.5}><Button fullWidth variant={project.id === activeProjectId ? 'outlined' : 'contained'} endIcon={<OpenInNewRounded />} onClick={() => onOpen(project)}>{project.id === activeProjectId ? '继续查看画布' : '打开画布'}</Button><Tooltip title="版本历史"><IconButton onClick={() => onVersions(project)}><HistoryOutlined fontSize="small" /></IconButton></Tooltip><Tooltip title="重新导入为新版本"><IconButton color="primary" onClick={() => onReimport(project)}><PublishedWithChangesOutlined fontSize="small" /></IconButton></Tooltip></Stack></Paper>)}
      </Box>}
    </Box>
  </Box>
}
