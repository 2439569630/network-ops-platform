export function normalizeFsmState(device) {
  const v =
    (device && (device.fsmState || device.fsm_state || device.rawStatus || device.raw_status)) ||
    ''
  return String(v || '').trim().toLowerCase()
}

export function normalizeConnectivity(device) {
  const v = device && (device.connectivity || device.status)
  const s = String(v || '').trim().toLowerCase()
  if (s === 'online' || s === 'offline') return s
  if (device && typeof device.online_status === 'boolean') return device.online_status ? 'online' : 'offline'
  if (device && typeof device.onlineStatus === 'boolean') return device.onlineStatus ? 'online' : 'offline'
  const label = normalizeDisplayStatus(device)
  if (label === '在线' || label === '采集中' || label === '检测中' || label === '恢复中' || label === '异常' || label === '重载中') return 'online'
  return 'offline'
}

export function normalizeDisplayStatus(device) {
  const v =
    (device && (device.displayStatus || device.display_status || device.status || '')) ||
    ''
  const s = String(v || '').trim()
  const low = s.toLowerCase()
  if (low === 'online' || low === 'offline') return ''
  return s
}

function getNextRetryAtEpoch(device) {
  const raw =
    (device && (device.next_retry_at_epoch || device.nextRetryAtEpoch || device.next_retry_at || device.nextRetryAt)) || 0
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
}

function getRetryAttempt(device) {
  const raw = (device && (device.retry_attempt || device.retryAttempt || 0)) || 0
  const n = Number(raw)
  return Number.isFinite(n) ? Math.max(0, Math.floor(n)) : 0
}

function formatCountdown(totalSeconds) {
  const s = Math.max(0, Math.floor(Number(totalSeconds) || 0))
  const sec = String(s % 60).padStart(2, '0')
  const minAll = Math.floor(s / 60)
  const min = String(minAll % 60).padStart(2, '0')
  const hour = Math.floor(minAll / 60)
  if (hour > 0) return `${hour}:${min}:${sec}`
  return `${min}:${sec}`
}

export function getDeviceStatusText(device, nowEpochMs) {
  const fsm = normalizeFsmState(device)
  const connectivity = normalizeConnectivity(device)
  const display = normalizeDisplayStatus(device)
  const reason = String((device && (device.fsmReason || device.fsm_reason || '')) || '')
  const stale = !!(device && device.stale)
  const nowMs = Number.isFinite(Number(nowEpochMs)) ? Number(nowEpochMs) : Date.now()
  const nextRetryAt = getNextRetryAtEpoch(device)
  const retryInSeconds = nextRetryAt > 0 ? Math.max(0, Math.ceil(nextRetryAt * 1000 - nowMs) / 1000) : 0
  const retryCountdown = retryInSeconds > 0 ? formatCountdown(retryInSeconds) : ''
  const retryAttempt = getRetryAttempt(device)
  const retryAttemptText = retryAttempt > 0 ? `第${retryAttempt}次` : ''
  const nextRetryAttemptText = `第${retryAttempt + 1}次`

  if (fsm === 'retrying') {
    return retryAttemptText ? `重试中（${retryAttemptText}）` : '重试中'
  }
  if (fsm === 'backoff') {
    const left = retryCountdown ? `${retryCountdown}后重试` : '等待重试'
    return `等待重试（${left} · ${nextRetryAttemptText}）`
  }

  if (connectivity !== 'offline') {
    if (display) return stale ? `${display}（过期）` : display
    if (fsm === 'online') return '在线'
    if (fsm === 'recovering') return '恢复中'
    if (fsm === 'degraded') return '异常'
    if (fsm === 'checking') return '检测中'
    if (fsm === 'collecting') return '采集中'
    if (fsm === 'reloading') return '重载中'
    if (fsm === 'init') return '初始化中'
    return '在线'
  }

  const retrySuffix = retryCountdown ? `（${retryCountdown}后重试 · ${nextRetryAttemptText}）` : ''
  if (reason.includes('timeout')) return `连接超时${retrySuffix}`
  if (reason.includes('auth')) return `认证失败${retrySuffix}`
  if (reason.includes('unreachable')) return `不可达${retrySuffix}`
  if (display && display !== '在线') return (stale ? `${display}（过期）` : display) + retrySuffix
  return `离线${retrySuffix}`
}

export function getDeviceStatusTagType(device) {
  const fsm = normalizeFsmState(device)
  const connectivity = normalizeConnectivity(device)
  const text = getDeviceStatusText(device)
  const stale = !!(device && device.stale)

  if (text === '无运行态' || text === '未知') return 'info'
  if (stale) return 'warning'
  if (fsm === 'retrying' || fsm === 'backoff') return 'warning'
  if (connectivity === 'offline') return 'danger'
  if (fsm === 'online') return 'success'
  if (fsm === 'recovering' || fsm === 'checking' || fsm === 'collecting' || fsm === 'reloading') return 'warning'
  if (fsm === 'degraded') return 'danger'
  if (fsm === 'init' || text === '待加载' || text === '初始化中') return 'info'
  return 'info'
}

export function isSshEnabled(device) {
  const fsm = normalizeFsmState(device)
  const connectivity = normalizeConnectivity(device)
  const display = normalizeDisplayStatus(device)
  const stale = !!(device && device.stale)
  const nextRetryAt = getNextRetryAtEpoch(device)

  if (connectivity !== 'online') return false
  if (stale) return false
  if (nextRetryAt > 0) return false
  if (fsm === 'offline' || fsm === 'init') return false
  if (fsm === 'checking' || fsm === 'collecting' || fsm === 'reloading' || fsm === 'retrying' || fsm === 'backoff') return false
  if (display === '待加载' || display === '初始化中' || display === '未知' || display === '无运行态') return false
  return true
}
