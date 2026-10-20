import { lazy, Suspense, useEffect, useState } from 'react'

type User = {
  id: string
  email: string
  username: string
  emailVerified: boolean
}

const Workspace = lazy(() => import('./App'))

function VisibilityIcon({ visible }: { visible: boolean }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.2 12s3.4-5.5 9.8-5.5S21.8 12 21.8 12 18.4 17.5 12 17.5 2.2 12 2.2 12Z" fill="none" stroke="currentColor" strokeWidth="1.8" /><circle cx="12" cy="12" r="2.7" fill="none" stroke="currentColor" strokeWidth="1.8" />{visible && <path d="m4 4 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />}</svg>
}

async function readApiJson<T>(response: Response): Promise<T> {
  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('application/json')) {
    await response.text()
    throw new Error('后端 API 未返回 JSON。请确认 Flask 服务正在 http://127.0.0.1:8123 运行，然后刷新页面重试。')
  }
  return response.json() as Promise<T>
}

function WorkspaceLoading() {
  return <main className="auth-shell"><div className="auth-card"><div className="auth-mark">S</div><h1>正在打开工作台</h1><p>正在加载画布、项目目录与图层检查器…</p><div className="auth-progress" /></div></main>
}

export default function AuthGate() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [identity, setIdentity] = useState('')
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [verificationCode, setVerificationCode] = useState('')
  const [password, setPassword] = useState('')
  const [passwordVisible, setPasswordVisible] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [resendSeconds, setResendSeconds] = useState(0)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    fetch('/api/auth/me')
      .then(async (response) => {
        if (response.status === 401) return null
        const result = await readApiJson<{ user?: User; error?: string }>(response)
        if (!response.ok || !result.user) throw new Error(result.error || '无法读取登录状态')
        return result.user
      })
      .then(setUser)
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!message && !error) return
    const timeout = window.setTimeout(() => { setMessage(''); setError('') }, error ? 6000 : 4000)
    return () => window.clearTimeout(timeout)
  }, [message, error])

  useEffect(() => {
    if (resendSeconds <= 0) return
    const interval = window.setInterval(() => setResendSeconds((seconds) => Math.max(0, seconds - 1)), 1000)
    return () => window.clearInterval(interval)
  }, [resendSeconds])

  const sendVerification = async () => {
    setError('')
    setMessage('')
    try {
      const response = await fetch('/api/auth/send-verification', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, username }) })
      const result = await readApiJson<{ message?: string; error?: string }>(response)
      if (!response.ok) throw new Error(result.error || '验证码发送失败')
      setMessage(result.message || '6 位验证码已发送，请查收邮箱')
      setResendSeconds(60)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '验证码发送失败')
    }
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const payload = mode === 'login'
        ? { identity, password }
        : { email, username, code: verificationCode, password }
      const response = await fetch(`/api/auth/${mode === 'login' ? 'login' : 'register'}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      const result = await readApiJson<{ user?: User; message?: string; error?: string }>(response)
      if (!response.ok || !result.user) throw new Error(result.error || '操作失败')
      setUser(result.user)
      setPassword('')
      setVerificationCode('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <WorkspaceLoading />
  if (user?.emailVerified) return <Suspense fallback={<WorkspaceLoading />}><Workspace /></Suspense>

  const isRegister = mode === 'register'
  return <main className="auth-shell"><section className="auth-card">
    {message && <div className="auth-toast success" role="status">{message}</div>}
    {error && <div className="auth-toast error" role="alert">{error}</div>}
    <div className="auth-mark">S</div>
    <p className="auth-kicker">Sketch Canvas</p>
    <h1>{isRegister ? '创建免费账户' : '欢迎回来'}</h1>
    <p className="auth-description">{isRegister ? '验证码仅保存于 Redis，10 分钟后自动过期；校验成功后才会创建账户。' : '导入、解析并检查你的 Sketch 设计稿。'}</p>
    <form className="auth-form" onSubmit={submit}>
      {isRegister && <><label>名称<input autoComplete="username" placeholder="你的名字" value={username} minLength={3} required onChange={(event) => setUsername(event.target.value)} /></label><label>邮箱<input type="email" autoComplete="email" placeholder="your@email.com" value={email} required onChange={(event) => setEmail(event.target.value)} /></label><div className="verification-group"><span>邮箱验证码</span><div className="verification-row"><input inputMode="numeric" autoComplete="one-time-code" placeholder="6 位验证码" value={verificationCode} maxLength={6} required onChange={(event) => setVerificationCode(event.target.value.replace(/\D/g, ''))} /><button className="auth-secondary" type="button" disabled={submitting || resendSeconds > 0} onClick={() => void sendVerification()}>{resendSeconds > 0 ? `${resendSeconds}s 后重发` : '发送邮箱验证码'}</button></div></div></>}
      {!isRegister && <label>邮箱或名称<input autoComplete="username" value={identity} required onChange={(event) => setIdentity(event.target.value)} /></label>}
      <label>密码<span className="password-field"><input type={passwordVisible ? 'text' : 'password'} autoComplete={isRegister ? 'new-password' : 'current-password'} placeholder={isRegister ? '请输入密码' : undefined} value={password} minLength={8} required onChange={(event) => setPassword(event.target.value)} /><button className="password-toggle" type="button" aria-label={passwordVisible ? '隐藏密码' : '显示密码'} title={passwordVisible ? '隐藏密码' : '显示密码'} onClick={() => setPasswordVisible((visible) => !visible)}><VisibilityIcon visible={passwordVisible} /></button></span></label>
      <button className="auth-button" disabled={submitting}>{submitting ? '请稍候…' : isRegister ? '创建账号' : '登录工作台'}</button>
    </form>
    <button className="auth-link" type="button" onClick={() => { setMode((current) => current === 'login' ? 'register' : 'login'); setPassword(''); setVerificationCode(''); setError(''); setMessage('') }}>{isRegister ? '已有账号？去登录' : '没有账户？创建一个免费账户'}</button>
  </section></main>
}
