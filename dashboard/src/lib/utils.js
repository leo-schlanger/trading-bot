import { clsx } from "clsx"
import { twMerge } from "tailwind-merge"
import { format, formatDistanceToNow, isValid } from "date-fns"

export function cn(...inputs) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(value, options = {}) {
  if (value === null || value === undefined) return '--'
  const { compact = false, showSign = false } = options

  const formatter = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: value >= 1000 ? 0 : 2,
    maximumFractionDigits: value >= 1000 ? 0 : 2,
    ...(compact && { notation: 'compact' })
  })

  const formatted = formatter.format(Math.abs(value))
  if (showSign && value > 0) return `+${formatted}`
  if (value < 0) return `-${formatted}`
  return formatted
}

export function formatPercent(value, decimals = 1) {
  if (value === null || value === undefined) return '--'
  const percent = (value * 100).toFixed(decimals)
  return `${percent}%`
}

export function formatDate(date, formatStr = 'PPp') {
  if (!date) return '--'
  const d = new Date(date)
  if (!isValid(d)) return '--'

  // If it's today, show relative time
  const now = new Date()
  const diffHours = (now - d) / (1000 * 60 * 60)

  if (diffHours < 24) {
    return formatDistanceToNow(d, { addSuffix: true })
  }

  return format(d, formatStr)
}

export function formatDateShort(date) {
  if (!date) return '--'
  const d = new Date(date)
  if (!isValid(d)) return '--'
  return format(d, 'MMM d, HH:mm')
}

export function formatReason(reason) {
  const map = {
    'ema_bullish': 'EMA Alignment Bullish',
    'ema_bearish': 'EMA Alignment Bearish',
    'macd_cross_up': 'MACD Cross Up',
    'macd_cross_down': 'MACD Cross Down',
    'macd_momentum_up': 'MACD Momentum Up',
    'macd_momentum_down': 'MACD Momentum Down',
    'supertrend_bullish': 'Supertrend Bullish',
    'supertrend_bearish': 'Supertrend Bearish',
    'adx_strong_up': 'ADX Strong Uptrend',
    'adx_strong_down': 'ADX Strong Downtrend',
    'rsi_bullish': 'RSI Bullish Zone',
    'rsi_bearish': 'RSI Bearish Zone',
    'rsi_oversold': 'RSI Oversold',
    'rsi_overbought': 'RSI Overbought',
    'bb_oversold': 'BB Oversold',
    'bb_overbought': 'BB Overbought',
    'volume_confirm_up': 'Volume Confirms Up',
    'volume_confirm_down': 'Volume Confirms Down',
    'trap_warning_short': 'Trap Warning (Short)',
    'trap_warning_long': 'Trap Warning (Long)',
    'insufficient_confirmations': 'Insufficient Confirmations',
  }
  return map[reason] || reason.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

export function formatTrap(trap) {
  const map = {
    'bull_trap': 'Bull Trap',
    'bear_trap': 'Bear Trap',
    'fake_breakout_up': 'Fake Breakout (Up)',
    'fake_breakout_down': 'Fake Breakout (Down)',
    'bullish_divergence': 'Bullish Divergence',
    'bearish_divergence': 'Bearish Divergence',
    'exhaustion_top': 'Exhaustion at Top',
    'exhaustion_bottom': 'Exhaustion at Bottom',
    'stop_hunt': 'Stop Hunt',
    'volume_dry_up': 'Volume Drying Up',
  }
  return map[trap] || trap.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

export function getSignalColor(action) {
  switch (action) {
    case 'LONG':
      return 'success'
    case 'SHORT':
      return 'danger'
    case 'BLOCKED':
      return 'warning'
    default:
      return 'secondary'
  }
}

export function getRegimeColor(regime) {
  switch (regime?.toLowerCase()) {
    case 'bull':
      return 'success'
    case 'bear':
      return 'danger'
    case 'sideways':
      return 'warning'
    case 'correction':
      return 'warning'
    default:
      return 'secondary'
  }
}

export function truncateAddress(address, chars = 4) {
  if (!address) return ''
  return `${address.slice(0, chars)}...${address.slice(-chars)}`
}

export function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}
