import React, { useState, useEffect, useRef } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn, formatCurrency, formatPercent, formatDate, formatReason, formatTrap } from '@/lib/utils'
import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, BarChart, Bar, ComposedChart, ReferenceLine
} from 'recharts'
import {
  TrendingUp, TrendingDown, Minus, AlertTriangle, CheckCircle, XCircle,
  RefreshCw, DollarSign, Activity, Shield, BarChart3, Clock, Target,
  ArrowUpRight, ArrowDownRight, AlertCircle, Lock, Zap, Eye, EyeOff,
  Wallet, PieChart as PieChartIcon, Menu, X, Bitcoin, Layers, Brain,
  ChevronRight, Flame, Gauge, Timer, Crosshair
} from 'lucide-react'

const API_BASE = '/api'
const INITIAL_CAPITAL = 500 // Default initial capital

// Theme colors
const COLORS = {
  success: '#22c55e',
  danger: '#ef4444',
  warning: '#f59e0b',
  primary: '#3b82f6',
  purple: '#8b5cf6',
  cyan: '#06b6d4',
  pink: '#ec4899',
}

// Animated number component
const AnimatedNumber = ({ value, prefix = '', suffix = '', decimals = 2 }) => {
  const [displayValue, setDisplayValue] = useState(value)
  const prevValueRef = useRef(value)

  useEffect(() => {
    const start = prevValueRef.current
    const end = value
    prevValueRef.current = value

    if (start === end) return

    const duration = 500
    const startTime = Date.now()
    let animationId

    const animate = () => {
      const now = Date.now()
      const progress = Math.min((now - startTime) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplayValue(start + (end - start) * eased)
      if (progress < 1) {
        animationId = requestAnimationFrame(animate)
      }
    }
    animate()

    return () => {
      if (animationId) cancelAnimationFrame(animationId)
    }
  }, [value])

  return <span>{prefix}{displayValue.toFixed(decimals)}{suffix}</span>
}

// Sparkline component
let sparklineIdCounter = 0
const Sparkline = ({ data, color = COLORS.primary, height = 40 }) => {
  const [gradientId] = useState(() => `spark-${++sparklineIdCounter}`)

  if (!data || data.length < 2) return null

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.3} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={1.5}
          fill={`url(#${gradientId})`}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

// Progress bar for SL/TP
const PositionProgressBar = ({ currentPrice, entryPrice, stopLoss, takeProfit, direction }) => {
  const isLong = direction === 'LONG'

  // Calculate position on the scale (0 = SL, 100 = TP)
  let progress
  if (isLong) {
    const range = takeProfit - stopLoss
    progress = ((currentPrice - stopLoss) / range) * 100
  } else {
    const range = stopLoss - takeProfit
    progress = ((stopLoss - currentPrice) / range) * 100
  }

  progress = Math.max(0, Math.min(100, progress))

  // Entry point position
  let entryPosition
  if (isLong) {
    entryPosition = ((entryPrice - stopLoss) / (takeProfit - stopLoss)) * 100
  } else {
    entryPosition = ((stopLoss - entryPrice) / (stopLoss - takeProfit)) * 100
  }

  const isProfitable = isLong ? currentPrice > entryPrice : currentPrice < entryPrice

  return (
    <div className="relative w-full">
      <div className="flex justify-between text-xs mb-1">
        <span className="text-danger font-medium">SL: {formatCurrency(stopLoss)}</span>
        <span className="text-success font-medium">TP: {formatCurrency(takeProfit)}</span>
      </div>
      <div className="relative h-3 bg-secondary rounded-full overflow-hidden">
        {/* Background gradient */}
        <div className="absolute inset-0 bg-gradient-to-r from-danger/20 via-warning/20 to-success/20" />

        {/* Entry marker */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-muted-foreground/50 z-10"
          style={{ left: `${entryPosition}%` }}
        />

        {/* Current price indicator */}
        <div
          className={cn(
            "absolute top-0 bottom-0 w-3 h-3 rounded-full border-2 border-background shadow-lg transition-all duration-300 -translate-x-1/2",
            isProfitable ? "bg-success" : "bg-danger"
          )}
          style={{ left: `${progress}%` }}
        />
      </div>
      <div className="flex justify-between text-xs mt-1 text-muted-foreground">
        <span>Loss Zone</span>
        <span className="text-foreground font-medium">
          Entry: {formatCurrency(entryPrice)}
        </span>
        <span>Profit Zone</span>
      </div>
    </div>
  )
}

// Custom tooltip
const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="glass-panel p-3 rounded-xl shadow-2xl border border-white/10">
        <p className="text-xs text-muted-foreground mb-1">{label}</p>
        {payload.map((entry, index) => (
          <p key={index} className="text-sm font-semibold" style={{ color: entry.color }}>
            {entry.name}: {typeof entry.value === 'number' ?
              (entry.dataKey === 'equity' || entry.dataKey === 'pnl' ? formatCurrency(entry.value) : entry.value.toFixed(2))
              : entry.value}
          </p>
        ))}
      </div>
    )
  }
  return null
}

// Metric Card with glass effect
const MetricCard = ({ title, value, subtitle, icon: Icon, trend, trendValue, color = 'primary', sparkData, className }) => (
  <Card className={cn(
    "glass-card group hover:scale-[1.02] transition-all duration-300 overflow-hidden",
    className
  )}>
    <div className={cn(
      "absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300",
      "bg-gradient-to-br from-white/5 to-transparent"
    )} />
    <CardContent className="p-4 relative">
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{title}</p>
          <p className="text-2xl font-bold mt-1 tabular-nums">{value}</p>
          {subtitle && <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>}
        </div>
        <div className={cn(
          "w-10 h-10 rounded-xl flex items-center justify-center glass-panel",
          color === 'success' ? "text-success" :
          color === 'danger' ? "text-danger" :
          color === 'warning' ? "text-warning" :
          color === 'purple' ? "text-purple-500" :
          "text-primary"
        )}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
      {sparkData && sparkData.length > 1 && (
        <div className="h-8 -mx-1 mt-2">
          <Sparkline
            data={sparkData}
            color={color === 'success' ? COLORS.success : color === 'danger' ? COLORS.danger : COLORS.primary}
          />
        </div>
      )}
      {trend !== undefined && (
        <div className={cn(
          "flex items-center gap-1 mt-2 text-xs font-medium",
          trend >= 0 ? "text-success" : "text-danger"
        )}>
          {trend >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
          <span>{trend >= 0 ? '+' : ''}{trendValue}</span>
        </div>
      )}
    </CardContent>
  </Card>
)

// Signal Badge
const SignalBadge = ({ action, size = 'default' }) => {
  const config = {
    'LONG': { color: 'success', icon: TrendingUp, bg: 'bg-success/10 text-success border-success/20' },
    'SHORT': { color: 'danger', icon: TrendingDown, bg: 'bg-danger/10 text-danger border-danger/20' },
    'HOLD': { color: 'secondary', icon: Minus, bg: 'bg-secondary text-muted-foreground border-border' },
    'BLOCKED': { color: 'warning', icon: AlertTriangle, bg: 'bg-warning/10 text-warning border-warning/20' },
  }
  const { icon: Icon, bg } = config[action] || config['HOLD']

  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border font-medium",
      bg,
      size === 'lg' && "text-base px-4 py-2"
    )}>
      <Icon className={cn("w-3.5 h-3.5", size === 'lg' && "w-4 h-4")} />
      {action}
    </span>
  )
}

// Live Price Badge
const LivePrice = ({ symbol, price, change }) => (
  <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl glass-panel">
    <div className={cn(
      "w-8 h-8 rounded-lg flex items-center justify-center",
      symbol === 'BTC' ? "bg-gradient-to-br from-yellow-500 to-orange-500" : "bg-gradient-to-br from-blue-500 to-purple-500"
    )}>
      {symbol === 'BTC' ? <Bitcoin className="w-4 h-4 text-white" /> : <Layers className="w-4 h-4 text-white" />}
    </div>
    <div>
      <p className="text-sm font-semibold">{symbol}</p>
      <p className="text-xs text-muted-foreground tabular-nums">{formatCurrency(price)}</p>
    </div>
    {change !== undefined && (
      <span className={cn(
        "text-xs font-semibold ml-1 tabular-nums",
        change >= 0 ? "text-success" : "text-danger"
      )}>
        {change >= 0 ? '+' : ''}{change.toFixed(2)}%
      </span>
    )}
  </div>
)

// Position Card (for Active Positions tab)
const PositionCard = ({ symbol, position, currentPrice }) => {
  if (!position || !position.entry_price) return null

  const entryPrice = position.entry_price
  const isLong = position.direction === 'LONG'
  const priceDiff = currentPrice - entryPrice
  // Use size if available, otherwise calculate from value/entry_price
  const positionSize = position.size || (position.value / entryPrice)
  const unrealizedPnL = isLong ? priceDiff * positionSize : -priceDiff * positionSize
  const unrealizedPnLPct = position.value > 0 ? (unrealizedPnL / position.value) * 100 : 0
  const isProfitable = unrealizedPnL >= 0

  // Time open
  const entryTime = new Date(position.entry_time)
  const now = new Date()
  const hoursOpen = Math.floor((now - entryTime) / (1000 * 60 * 60))
  const daysOpen = Math.floor(hoursOpen / 24)
  const timeString = daysOpen > 0 ? `${daysOpen}d ${hoursOpen % 24}h` : `${hoursOpen}h`

  // Distance to SL/TP (always positive, showing how far away)
  const distanceToSL = Math.abs(isLong
    ? ((currentPrice - position.stop_loss) / currentPrice * 100)
    : ((position.stop_loss - currentPrice) / currentPrice * 100))
  const distanceToTP = Math.abs(isLong
    ? ((position.take_profit - currentPrice) / currentPrice * 100)
    : ((currentPrice - position.take_profit) / currentPrice * 100))

  return (
    <Card className="glass-card overflow-hidden group">
      {/* Top accent bar */}
      <div className={cn(
        "h-1",
        isLong ? "bg-gradient-to-r from-success via-emerald-400 to-success" : "bg-gradient-to-r from-danger via-red-400 to-danger"
      )} />

      <CardContent className="p-5">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className={cn(
              "w-12 h-12 rounded-xl flex items-center justify-center shadow-lg",
              symbol === 'BTC' ? "bg-gradient-to-br from-yellow-500 to-orange-500" : "bg-gradient-to-br from-blue-500 to-purple-500"
            )}>
              {symbol === 'BTC' ? <Bitcoin className="w-6 h-6 text-white" /> : <Layers className="w-6 h-6 text-white" />}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-bold">{symbol}-PERP</h3>
                <SignalBadge action={position.direction} />
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                <Timer className="w-3 h-3" />
                <span>Open for {timeString}</span>
              </div>
            </div>
          </div>

          {/* Unrealized P&L */}
          <div className={cn(
            "text-right p-3 rounded-xl",
            isProfitable ? "bg-success/10" : "bg-danger/10"
          )}>
            <p className="text-xs text-muted-foreground mb-0.5">Unrealized P&L</p>
            <p className={cn(
              "text-xl font-bold tabular-nums",
              isProfitable ? "text-success" : "text-danger"
            )}>
              {isProfitable ? '+' : ''}{formatCurrency(unrealizedPnL)}
            </p>
            <p className={cn(
              "text-xs font-medium tabular-nums",
              isProfitable ? "text-success/70" : "text-danger/70"
            )}>
              {isProfitable ? '+' : ''}{unrealizedPnLPct.toFixed(2)}%
            </p>
          </div>
        </div>

        {/* Price Progress Bar */}
        <div className="mb-4">
          <PositionProgressBar
            currentPrice={currentPrice}
            entryPrice={entryPrice}
            stopLoss={position.stop_loss}
            takeProfit={position.take_profit}
            direction={position.direction}
          />
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="p-3 rounded-xl bg-secondary/50">
            <p className="text-xs text-muted-foreground">Entry Price</p>
            <p className="font-semibold tabular-nums">{formatCurrency(entryPrice)}</p>
          </div>
          <div className="p-3 rounded-xl bg-secondary/50">
            <p className="text-xs text-muted-foreground">Current Price</p>
            <p className={cn("font-semibold tabular-nums", isProfitable ? "text-success" : "text-danger")}>
              {formatCurrency(currentPrice)}
            </p>
          </div>
          <div className="p-3 rounded-xl bg-secondary/50">
            <p className="text-xs text-muted-foreground">Position Size</p>
            <p className="font-semibold tabular-nums">{formatCurrency(position.value)}</p>
          </div>
          <div className="p-3 rounded-xl bg-secondary/50">
            <p className="text-xs text-muted-foreground">Leverage</p>
            <p className="font-semibold">{position.leverage || '1'}x</p>
          </div>
        </div>

        {/* Risk Metrics */}
        <div className="grid grid-cols-2 gap-3 mt-3">
          <div className="p-3 rounded-xl bg-danger/5 border border-danger/10">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-danger/70">Distance to SL</p>
                <p className="font-semibold text-danger tabular-nums">{distanceToSL.toFixed(2)}%</p>
              </div>
              <Crosshair className="w-4 h-4 text-danger/50" />
            </div>
          </div>
          <div className="p-3 rounded-xl bg-success/5 border border-success/10">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-success/70">Distance to TP</p>
                <p className="font-semibold text-success tabular-nums">{distanceToTP.toFixed(2)}%</p>
              </div>
              <Target className="w-4 h-4 text-success/50" />
            </div>
          </div>
        </div>

        {/* Trade Info */}
        {position.strategy && (
          <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
            <Brain className="w-3 h-3" />
            <span>Strategy: {position.strategy}</span>
            <span className="text-border">|</span>
            <span>Regime: {position.regime}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// Asset Signal Card
const AssetSignalCard = ({ symbol, signal }) => {
  if (!signal) return null

  return (
    <Card className="glass-card overflow-hidden group hover:scale-[1.01] transition-all duration-300">
      <div className={cn(
        "h-1",
        signal.action === 'LONG' ? "bg-gradient-to-r from-success to-emerald-400" :
        signal.action === 'SHORT' ? "bg-gradient-to-r from-danger to-red-400" :
        "bg-gradient-to-r from-muted to-muted-foreground/20"
      )} />
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={cn(
              "w-10 h-10 rounded-xl flex items-center justify-center shadow-lg",
              symbol === 'BTC' ? "bg-gradient-to-br from-yellow-500 to-orange-500" : "bg-gradient-to-br from-blue-500 to-purple-500"
            )}>
              {symbol === 'BTC' ? <Bitcoin className="w-5 h-5 text-white" /> : <Layers className="w-5 h-5 text-white" />}
            </div>
            <div>
              <CardTitle className="text-lg">{symbol}-PERP</CardTitle>
              <CardDescription className="tabular-nums">{formatCurrency(signal.price)}</CardDescription>
            </div>
          </div>
          <SignalBadge action={signal.action} />
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-2 mt-2">
          <div className="p-2.5 rounded-lg bg-secondary/50">
            <p className="text-xs text-muted-foreground">Regime</p>
            <p className="font-semibold capitalize">{signal.regime}</p>
          </div>
          <div className="p-2.5 rounded-lg bg-secondary/50">
            <p className="text-xs text-muted-foreground">Confidence</p>
            <div className="flex items-center gap-2">
              <p className="font-semibold">{(() => {
                const conf = signal.confidence || 0
                // Handle both 0-1 and 0-100 formats
                return conf > 1 ? `${conf.toFixed(0)}%` : formatPercent(conf)
              })()}</p>
              <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
                <div
                  className={cn(
                    "h-full rounded-full transition-all",
                    (signal.confidence || 0) >= 0.7 ? "bg-success" : (signal.confidence || 0) >= 0.5 ? "bg-warning" : "bg-danger"
                  )}
                  style={{ width: `${((signal.confidence || 0) > 1 ? signal.confidence : (signal.confidence || 0) * 100)}%` }}
                />
              </div>
            </div>
          </div>
          <div className="p-2.5 rounded-lg bg-danger/10">
            <p className="text-xs text-danger">Stop Loss</p>
            <p className="font-semibold text-danger tabular-nums">{formatCurrency(signal.stop_loss)}</p>
          </div>
          <div className="p-2.5 rounded-lg bg-success/10">
            <p className="text-xs text-success">Take Profit</p>
            <p className="font-semibold text-success tabular-nums">{formatCurrency(signal.take_profit)}</p>
          </div>
        </div>

        {/* Reasons */}
        <div className="mt-3 flex flex-wrap gap-1">
          {(signal.reasons || []).slice(0, 4).map((reason, i) => (
            <Badge key={i} variant="outline" className="text-xs">
              {formatReason(reason)}
            </Badge>
          ))}
        </div>

        {/* Traps Warning */}
        {signal.traps_detected?.length > 0 && (
          <div className="mt-3 p-2 rounded-lg bg-warning/10 border border-warning/20 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-warning flex-shrink-0" />
            <span className="text-xs text-warning">
              Trap detected: {signal.traps_detected.join(', ')}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// Risk Gauge Component
const RiskGauge = ({ currentDrawdown, maxDrawdown = 20 }) => {
  const percentage = Math.min((currentDrawdown / maxDrawdown) * 100, 100)
  const riskLevel = percentage < 30 ? 'low' : percentage < 60 ? 'medium' : 'high'

  return (
    <div className="w-full">
      <div className="flex justify-between text-xs mb-2">
        <span className="text-muted-foreground">Drawdown Risk</span>
        <span className={cn(
          "font-semibold",
          riskLevel === 'low' ? "text-success" : riskLevel === 'medium' ? "text-warning" : "text-danger"
        )}>
          {currentDrawdown.toFixed(1)}% / {maxDrawdown}%
        </span>
      </div>
      <div className="relative h-2 bg-secondary rounded-full overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-success via-warning to-danger" />
        <div
          className="absolute inset-y-0 right-0 bg-background transition-all duration-500"
          style={{ width: `${100 - percentage}%` }}
        />
      </div>
      <div className="flex justify-between text-xs mt-1 text-muted-foreground">
        <span>Safe</span>
        <span>Caution</span>
        <span>Danger</span>
      </div>
    </div>
  )
}

// Main App
export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(null)
  const [lastUpdate, setLastUpdate] = useState(null)
  const [showPassword, setShowPassword] = useState(false)
  const [activeTab, setActiveTab] = useState('overview')
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    const token = sessionStorage.getItem('auth_token')
    if (token) {
      setIsAuthenticated(true)
      fetchData(token)
    }
  }, [])

  // Auto refresh every 5 minutes
  useEffect(() => {
    if (!isAuthenticated) return
    const interval = setInterval(() => {
      const token = sessionStorage.getItem('auth_token')
      if (token) fetchData(token)
    }, 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [isAuthenticated])

  const authenticate = async () => {
    setError('')
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/auth`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password })
      })
      const result = await res.json()
      if (result.success) {
        sessionStorage.setItem('auth_token', result.token)
        setIsAuthenticated(true)
        fetchData(result.token)
      } else {
        setError('Invalid password')
      }
    } catch (e) {
      setError('Connection error')
    }
    setLoading(false)
  }

  const fetchData = async (token) => {
    setLoading(true)
    try {
      const headers = { 'Authorization': `Bearer ${token}` }
      const [stateRes, historyRes, metricsRes] = await Promise.all([
        fetch(`${API_BASE}/state`, { headers }),
        fetch(`${API_BASE}/history`, { headers }),
        fetch(`${API_BASE}/metrics`, { headers })
      ])

      if (stateRes.status === 401) {
        sessionStorage.removeItem('auth_token')
        setIsAuthenticated(false)
        return
      }

      const state = await stateRes.json()
      const history = await historyRes.json()
      const metrics = await metricsRes.json()

      setData({ state, history, metrics })
      setLastUpdate(new Date())
    } catch (e) {
      console.error('Error fetching data:', e)
    }
    setLoading(false)
  }

  const refresh = () => {
    const token = sessionStorage.getItem('auth_token')
    if (token) fetchData(token)
  }

  const logout = () => {
    sessionStorage.removeItem('auth_token')
    setIsAuthenticated(false)
    setData(null)
  }

  // Login Screen
  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4 bg-gradient-to-br from-background via-background to-primary/5">
        <div className="absolute inset-0 overflow-hidden">
          <div className="absolute -top-1/2 -left-1/2 w-full h-full bg-gradient-to-br from-primary/20 to-transparent rounded-full blur-3xl animate-pulse" />
          <div className="absolute -bottom-1/2 -right-1/2 w-full h-full bg-gradient-to-tl from-purple-500/20 to-transparent rounded-full blur-3xl animate-pulse delay-1000" />
        </div>

        <Card className="w-full max-w-md relative glass-card border-primary/20">
          <CardHeader className="text-center relative">
            <div className="mx-auto mb-4 w-20 h-20 rounded-2xl bg-gradient-to-br from-primary via-purple-500 to-pink-500 flex items-center justify-center shadow-2xl shadow-primary/30 animate-float">
              <BarChart3 className="w-10 h-10 text-white" />
            </div>
            <CardTitle className="text-3xl font-bold bg-gradient-to-r from-foreground via-foreground/80 to-foreground bg-clip-text">
              Trading Bot
            </CardTitle>
            <CardDescription className="text-muted-foreground">
              Intelligent Trading Dashboard
            </CardDescription>
          </CardHeader>

          <CardContent className="relative">
            <div className="space-y-4">
              <div className="relative group">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground transition-colors group-focus-within:text-primary" />
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && authenticate()}
                  placeholder="Enter password"
                  className="w-full pl-10 pr-10 py-3 rounded-xl border bg-secondary/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>

              <Button
                onClick={authenticate}
                className="w-full py-6 bg-gradient-to-r from-primary via-purple-500 to-pink-500 hover:opacity-90 shadow-lg shadow-primary/25 transition-all hover:shadow-xl hover:shadow-primary/30"
                disabled={loading}
              >
                {loading ? (
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Zap className="w-4 h-4 mr-2" />
                )}
                {loading ? 'Authenticating...' : 'Access Dashboard'}
              </Button>

              {error && (
                <div className="flex items-center gap-2 p-3 rounded-xl bg-danger/10 border border-danger/20 animate-shake">
                  <AlertCircle className="w-4 h-4 text-danger" />
                  <p className="text-sm text-danger">{error}</p>
                </div>
              )}
            </div>

            <div className="mt-6 pt-6 border-t border-border/50">
              <p className="text-xs text-center text-muted-foreground">
                Protected access • Drift Protocol • Paper Trading
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Extract data with consistent fallbacks
  const state = data?.state?.state || {}
  const lastSignals = state.last_signals || {}
  const trades = data?.history?.trades || []
  const openPositions = data?.state?.positions || {}
  const metrics = data?.metrics?.metrics || {}
  const portfolioSummary = data?.state?.portfolioSummary || {}
  const safetyStatus = data?.state?.safetyStatus || {}
  const decisionLog = data?.state?.decisions || []

  // Calculate metrics with consistent initial capital
  const totalPnL = state.total_pnl || 0
  const capital = state.capital || INITIAL_CAPITAL
  const peakCapital = state.risk_state?.peak || INITIAL_CAPITAL
  const currentDrawdown = peakCapital > 0 ? ((peakCapital - capital) / peakCapital) * 100 : 0
  const openPositionsCount = Object.keys(openPositions).length

  // Calculate total unrealized P&L
  const totalUnrealizedPnL = Object.entries(openPositions).reduce((sum, [symbol, pos]) => {
    if (!pos || !pos.entry_price) return sum
    const currentPrice = lastSignals[symbol]?.price || pos.entry_price
    const isLong = pos.direction === 'LONG'
    const priceDiff = currentPrice - pos.entry_price
    // Calculate position size from value/entry_price, then compute P&L
    const positionSize = pos.size || (pos.value / pos.entry_price)
    const pnl = isLong ? priceDiff * positionSize : -priceDiff * positionSize
    return sum + pnl
  }, 0)

  // Equity curve - use API data if available, otherwise calculate from trades
  const apiEquityCurve = data?.metrics?.equityCurve
  const equityCurve = apiEquityCurve && apiEquityCurve.length > 0
    ? apiEquityCurve.map(point => ({
        date: point.date || new Date(point.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        equity: point.equity || point.value,
        pnl: point.pnl || 0,
        value: point.equity || point.value
      }))
    : trades.reduce((acc, trade) => {
        const prevEquity = acc.length > 0 ? acc[acc.length - 1].equity : INITIAL_CAPITAL
        const pnl = trade.pnl || 0
        acc.push({
          date: new Date(trade.timestamp || trade.exit_time).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
          equity: prevEquity + pnl,
          pnl,
          value: prevEquity + pnl
        })
        return acc
      }, [{ date: 'Start', equity: INITIAL_CAPITAL, pnl: 0, value: INITIAL_CAPITAL }])

  // P&L sparkline data
  const pnlSparkData = equityCurve.map(d => ({ value: d.equity }))

  // Regime distribution
  const regimeData = trades.reduce((acc, trade) => {
    const regime = trade.regime || 'unknown'
    acc[regime] = (acc[regime] || 0) + 1
    return acc
  }, {})
  const regimePieData = Object.entries(regimeData).map(([name, value]) => ({ name, value }))

  // Daily P&L chart
  const dailyPnLData = trades.reduce((acc, trade) => {
    const date = new Date(trade.exit_time || trade.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    acc[date] = (acc[date] || 0) + (trade.pnl || 0)
    return acc
  }, {})
  const dailyPnL = Object.entries(dailyPnLData).map(([date, pnl]) => ({ date, pnl }))

  // Drawdown chart
  let drawdownPeak = INITIAL_CAPITAL
  const drawdownData = equityCurve.map(point => {
    drawdownPeak = Math.max(drawdownPeak, point.equity)
    const dd = drawdownPeak > 0 ? ((drawdownPeak - point.equity) / drawdownPeak) * 100 : 0
    return { date: point.date, drawdown: -dd, equity: point.equity }
  })

  const tabs = [
    { id: 'overview', label: 'Overview', icon: Activity },
    { id: 'positions', label: 'Positions', icon: Crosshair, badge: openPositionsCount },
    { id: 'signals', label: 'Signals', icon: Zap },
    { id: 'trades', label: 'Trades', icon: Clock },
    { id: 'analytics', label: 'Analytics', icon: PieChartIcon },
  ]

  return (
    <div className="min-h-screen bg-background">
      {/* Animated background */}
      <div className="fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-primary/5 rounded-full blur-3xl" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-purple-500/5 rounded-full blur-3xl" />
      </div>

      {/* Header */}
      <header className="sticky top-0 z-50 border-b glass-panel">
        <div className="container mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden p-2 rounded-lg hover:bg-secondary transition-colors"
              >
                <Menu className="w-5 h-5" />
              </button>

              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary via-purple-500 to-pink-500 flex items-center justify-center shadow-lg shadow-primary/25">
                  <BarChart3 className="w-5 h-5 text-white" />
                </div>
                <div className="hidden sm:block">
                  <h1 className="text-lg font-bold">Trading Bot</h1>
                  <div className="flex items-center gap-2">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-success"></span>
                    </span>
                    <span className="text-xs text-muted-foreground">Paper Trading</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Live Prices */}
            <div className="hidden md:flex items-center gap-2">
              {Object.entries(lastSignals).filter(([_, signal]) => signal.price != null).map(([symbol, signal]) => (
                <LivePrice
                  key={symbol}
                  symbol={symbol}
                  price={signal.price}
                />
              ))}
            </div>

            <div className="flex items-center gap-2">
              <span className="hidden sm:block text-xs text-muted-foreground">
                {lastUpdate ? `Updated ${formatDate(lastUpdate)}` : '--'}
              </span>
              <Button variant="outline" size="icon" onClick={refresh} disabled={loading} className="rounded-lg">
                <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
              </Button>
              <Button variant="ghost" size="icon" onClick={logout} className="rounded-lg">
                <X className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Sidebar - Mobile */}
        {sidebarOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setSidebarOpen(false)} />
            <nav className="absolute left-0 top-0 bottom-0 w-64 glass-panel border-r p-4 space-y-2">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => { setActiveTab(tab.id); setSidebarOpen(false) }}
                  className={cn(
                    "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left transition-all",
                    activeTab === tab.id ? "bg-primary/10 text-primary" : "hover:bg-secondary"
                  )}
                >
                  <tab.icon className="w-4 h-4" />
                  <span>{tab.label}</span>
                  {tab.badge > 0 && (
                    <span className="ml-auto bg-primary text-primary-foreground text-xs px-2 py-0.5 rounded-full">
                      {tab.badge}
                    </span>
                  )}
                </button>
              ))}
            </nav>
          </div>
        )}

        {/* Sidebar - Desktop */}
        <nav className="hidden lg:flex flex-col w-64 border-r glass-panel p-4 space-y-2 sticky top-[73px] h-[calc(100vh-73px)]">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left transition-all",
                activeTab === tab.id
                  ? "bg-gradient-to-r from-primary/20 to-purple-500/10 text-primary border-l-2 border-primary"
                  : "hover:bg-secondary"
              )}
            >
              <tab.icon className="w-4 h-4" />
              <span>{tab.label}</span>
              {tab.badge > 0 && (
                <span className="ml-auto bg-primary text-primary-foreground text-xs px-2 py-0.5 rounded-full animate-pulse">
                  {tab.badge}
                </span>
              )}
              <ChevronRight className={cn("w-4 h-4 ml-auto transition-transform", activeTab === tab.id && "rotate-90")} />
            </button>
          ))}

          <div className="flex-1" />

          {/* Risk Gauge */}
          <Card className="glass-card">
            <CardContent className="p-4">
              <RiskGauge currentDrawdown={currentDrawdown} maxDrawdown={20} />
            </CardContent>
          </Card>

          {/* Safety Status */}
          <Card className="glass-card">
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-2">
                <Shield className="w-4 h-4 text-muted-foreground" />
                <span className="text-sm font-medium">Safety Status</span>
              </div>
              <div className="flex items-center gap-2">
                {safetyStatus.blocked ? (
                  <><XCircle className="w-5 h-5 text-danger" /><span className="text-danger text-sm">BLOCKED</span></>
                ) : safetyStatus.warnings?.length > 0 ? (
                  <><AlertTriangle className="w-5 h-5 text-warning" /><span className="text-warning text-sm">WARNING</span></>
                ) : (
                  <><CheckCircle className="w-5 h-5 text-success" /><span className="text-success text-sm">All Systems OK</span></>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                Consecutive Losses: {state.consecutive_losses || 0}/3
              </p>
            </CardContent>
          </Card>
        </nav>

        {/* Main Content */}
        <main className="flex-1 p-4 lg:p-6 space-y-6 max-w-7xl">
          {/* Overview Tab */}
          {activeTab === 'overview' && (
            <>
              {/* Key Metrics */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <MetricCard
                  title="Portfolio Value"
                  value={formatCurrency(capital)}
                  subtitle={`Peak: ${formatCurrency(peakCapital)}`}
                  icon={Wallet}
                  trend={totalPnL >= 0 ? 1 : -1}
                  trendValue={formatCurrency(totalPnL)}
                  color={totalPnL >= 0 ? 'success' : 'danger'}
                  sparkData={pnlSparkData}
                />
                <MetricCard
                  title="Market Regime"
                  value={(state.last_regime || 'unknown').toUpperCase()}
                  subtitle="ML Detection"
                  icon={Brain}
                  color={
                    state.last_regime === 'bull' ? 'success' :
                    state.last_regime === 'bear' ? 'danger' : 'warning'
                  }
                />
                <MetricCard
                  title="Open Positions"
                  value={openPositionsCount}
                  subtitle={totalUnrealizedPnL !== 0 ?
                    `Unrealized: ${totalUnrealizedPnL >= 0 ? '+' : ''}${formatCurrency(totalUnrealizedPnL)}` :
                    'No active trades'}
                  icon={Crosshair}
                  color={openPositionsCount > 0 ? (totalUnrealizedPnL >= 0 ? 'success' : 'danger') : 'primary'}
                />
                <MetricCard
                  title="Win Rate"
                  value={(() => {
                    const winRate = portfolioSummary.winRate ?? metrics.win_rate
                    if (winRate === undefined || winRate === null) return '--'
                    // Handle both 0-1 and 0-100 formats
                    return winRate > 1 ? `${winRate.toFixed(1)}%` : formatPercent(winRate)
                  })()}
                  subtitle={`W: ${portfolioSummary.winningTrades || 0} / L: ${portfolioSummary.losingTrades || 0}`}
                  icon={Target}
                  color="success"
                />
              </div>

              {/* Open Positions Alert */}
              {openPositionsCount > 0 && (
                <Card className="glass-card border-primary/30 overflow-hidden">
                  <div className="h-1 bg-gradient-to-r from-primary via-purple-500 to-pink-500" />
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
                          <Flame className="w-5 h-5 text-primary animate-pulse" />
                        </div>
                        <div>
                          <p className="font-semibold">{openPositionsCount} Active Position{openPositionsCount > 1 ? 's' : ''}</p>
                          <p className="text-sm text-muted-foreground">
                            Unrealized P&L:
                            <span className={cn("ml-1 font-semibold", totalUnrealizedPnL >= 0 ? "text-success" : "text-danger")}>
                              {totalUnrealizedPnL >= 0 ? '+' : ''}{formatCurrency(totalUnrealizedPnL)}
                            </span>
                          </p>
                        </div>
                      </div>
                      <Button
                        variant="outline"
                        onClick={() => setActiveTab('positions')}
                        className="gap-2"
                      >
                        View Positions
                        <ChevronRight className="w-4 h-4" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Asset Signals */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {Object.entries(lastSignals).map(([symbol, signal]) => (
                  <AssetSignalCard key={symbol} symbol={symbol} signal={signal} />
                ))}
                {Object.keys(lastSignals).length === 0 && (
                  <Card className="md:col-span-2 glass-card">
                    <CardContent className="py-12 text-center">
                      <Activity className="w-12 h-12 mx-auto text-muted-foreground/50 mb-4" />
                      <p className="text-muted-foreground">No signal data available yet</p>
                      <p className="text-xs text-muted-foreground mt-1">Wait for the next trading cycle</p>
                    </CardContent>
                  </Card>
                )}
              </div>

              {/* Equity & Drawdown Charts */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Equity Chart */}
                {equityCurve.length > 1 && (
                  <Card className="glass-card">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <TrendingUp className="w-4 h-4 text-primary" />
                        Equity Curve
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="h-48">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={equityCurve}>
                            <defs>
                              <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor={COLORS.primary} stopOpacity={0.3}/>
                                <stop offset="95%" stopColor={COLORS.primary} stopOpacity={0}/>
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                            <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={10} />
                            <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} tickFormatter={(v) => `$${v}`} />
                            <Tooltip content={<CustomTooltip />} />
                            <Area
                              type="monotone"
                              dataKey="equity"
                              stroke={COLORS.primary}
                              strokeWidth={2}
                              fill="url(#equityGradient)"
                              name="Equity"
                            />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Drawdown Chart */}
                {drawdownData.length > 1 && (
                  <Card className="glass-card">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <TrendingDown className="w-4 h-4 text-danger" />
                        Drawdown
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="h-48">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={drawdownData}>
                            <defs>
                              <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor={COLORS.danger} stopOpacity={0.3}/>
                                <stop offset="95%" stopColor={COLORS.danger} stopOpacity={0}/>
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                            <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={10} />
                            <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} tickFormatter={(v) => `${v}%`} />
                            <Tooltip content={<CustomTooltip />} />
                            <ReferenceLine y={-20} stroke={COLORS.danger} strokeDasharray="5 5" />
                            <Area
                              type="monotone"
                              dataKey="drawdown"
                              stroke={COLORS.danger}
                              strokeWidth={2}
                              fill="url(#drawdownGradient)"
                              name="Drawdown %"
                            />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </div>

              {/* Recent Decisions */}
              <Card className="glass-card">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Clock className="w-4 h-4" />
                    Recent Decisions
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {decisionLog.slice(-5).reverse().map((entry, i) => (
                      <div key={i} className="flex items-center gap-4 p-3 rounded-xl bg-secondary/30 hover:bg-secondary/50 transition-colors">
                        <div className={cn(
                          "w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0",
                          entry.action === 'LONG' ? "bg-success/10" :
                          entry.action === 'SHORT' ? "bg-danger/10" : "bg-secondary"
                        )}>
                          {entry.action === 'LONG' ? <TrendingUp className="w-5 h-5 text-success" /> :
                           entry.action === 'SHORT' ? <TrendingDown className="w-5 h-5 text-danger" /> :
                           <Minus className="w-5 h-5 text-muted-foreground" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{entry.symbol}</span>
                            <SignalBadge action={entry.action} />
                          </div>
                          <p className="text-xs text-muted-foreground truncate">
                            {entry.reasons?.slice(0, 2).map(formatReason).join(' • ')}
                          </p>
                        </div>
                        <div className="text-right text-xs text-muted-foreground">
                          <p className="font-medium">{(() => {
                            const conf = entry.confidence || 0
                            return conf > 1 ? `${conf.toFixed(0)}%` : formatPercent(conf)
                          })()}</p>
                          <p>{entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '--'}</p>
                        </div>
                      </div>
                    ))}
                    {decisionLog.length === 0 && (
                      <p className="text-center text-muted-foreground py-8">No decisions yet</p>
                    )}
                  </div>
                </CardContent>
              </Card>
            </>
          )}

          {/* Positions Tab */}
          {activeTab === 'positions' && (
            <>
              {/* Summary Stats */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <MetricCard
                  title="Open Positions"
                  value={openPositionsCount}
                  subtitle="Active trades"
                  icon={Crosshair}
                  color="primary"
                />
                <MetricCard
                  title="Total Exposure"
                  value={formatCurrency(Object.values(openPositions).reduce((sum, p) => sum + (p?.value || 0), 0))}
                  subtitle={(() => {
                    const totalExposure = Object.values(openPositions).reduce((sum, p) => sum + (p?.value || 0), 0)
                    const exposurePct = capital > 0 ? (totalExposure / capital) * 100 : 0
                    return `${exposurePct.toFixed(1)}% of capital`
                  })()}
                  icon={Gauge}
                  color="warning"
                />
                <MetricCard
                  title="Unrealized P&L"
                  value={`${totalUnrealizedPnL >= 0 ? '+' : ''}${formatCurrency(totalUnrealizedPnL)}`}
                  subtitle="Paper profit/loss"
                  icon={DollarSign}
                  color={totalUnrealizedPnL >= 0 ? 'success' : 'danger'}
                />
                <MetricCard
                  title="Avg Position Time"
                  value={openPositionsCount > 0 ? (() => {
                    const avgHours = Object.values(openPositions).reduce((sum, p) => {
                      return sum + (Date.now() - new Date(p.entry_time).getTime()) / (1000 * 60 * 60)
                    }, 0) / openPositionsCount
                    return avgHours >= 24 ? `${Math.floor(avgHours / 24)}d` : `${Math.floor(avgHours)}h`
                  })() : '--'}
                  subtitle="Holding duration"
                  icon={Timer}
                  color="purple"
                />
              </div>

              {/* Position Cards */}
              {openPositionsCount > 0 ? (
                <div className="space-y-4">
                  {Object.entries(openPositions).map(([symbol, position]) => (
                    <PositionCard
                      key={symbol}
                      symbol={symbol}
                      position={position}
                      currentPrice={lastSignals[symbol]?.price || position.entry_price}
                    />
                  ))}
                </div>
              ) : (
                <Card className="glass-card">
                  <CardContent className="py-16 text-center">
                    <div className="w-20 h-20 rounded-2xl bg-secondary/50 flex items-center justify-center mx-auto mb-4">
                      <Crosshair className="w-10 h-10 text-muted-foreground/50" />
                    </div>
                    <h3 className="text-lg font-semibold mb-2">No Active Positions</h3>
                    <p className="text-muted-foreground mb-4">
                      The bot is waiting for the right market conditions to enter a trade.
                    </p>
                    <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                      <Brain className="w-4 h-4" />
                      <span>Current Regime: <strong className="capitalize">{state.last_regime || 'Unknown'}</strong></span>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Quick Stats */}
              {trades.length > 0 && (
                <Card className="glass-card">
                  <CardHeader>
                    <CardTitle className="text-base">Position History Stats</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="p-3 rounded-xl bg-secondary/30">
                        <p className="text-xs text-muted-foreground">Total Trades</p>
                        <p className="text-xl font-bold">{trades.length}</p>
                      </div>
                      <div className="p-3 rounded-xl bg-secondary/30">
                        <p className="text-xs text-muted-foreground">Avg Holding Time</p>
                        <p className="text-xl font-bold">
                          {(() => {
                            const tradesWithTimes = trades.filter(t => t.entry_time && t.exit_time)
                            if (tradesWithTimes.length === 0) return '--'
                            const totalMs = tradesWithTimes.reduce((sum, t) => {
                              return sum + (new Date(t.exit_time) - new Date(t.entry_time))
                            }, 0)
                            const avgMs = totalMs / tradesWithTimes.length
                            const hours = avgMs / (1000 * 60 * 60)
                            if (isNaN(hours) || hours <= 0) return '--'
                            return hours >= 24 ? `${Math.floor(hours / 24)}d` : `${Math.floor(hours)}h`
                          })()}
                        </p>
                      </div>
                      <div className="p-3 rounded-xl bg-success/10">
                        <p className="text-xs text-success">Best Trade</p>
                        <p className="text-xl font-bold text-success">
                          {(() => {
                            const pnls = trades.filter(t => t.pnl !== undefined).map(t => t.pnl)
                            if (pnls.length === 0) return '--'
                            const best = Math.max(...pnls)
                            return `+${formatCurrency(best)}`
                          })()}
                        </p>
                      </div>
                      <div className="p-3 rounded-xl bg-danger/10">
                        <p className="text-xs text-danger">Worst Trade</p>
                        <p className="text-xl font-bold text-danger">
                          {(() => {
                            const pnls = trades.filter(t => t.pnl !== undefined).map(t => t.pnl)
                            if (pnls.length === 0) return '--'
                            const worst = Math.min(...pnls)
                            return formatCurrency(worst)
                          })()}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          )}

          {/* Signals Tab */}
          {activeTab === 'signals' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {Object.entries(lastSignals).map(([symbol, signal]) => (
                <Card key={symbol} className="glass-card overflow-hidden">
                  <div className={cn(
                    "h-2",
                    signal.action === 'LONG' ? "bg-gradient-to-r from-success via-emerald-400 to-success" :
                    signal.action === 'SHORT' ? "bg-gradient-to-r from-danger via-red-400 to-danger" :
                    "bg-gradient-to-r from-muted to-muted-foreground/20"
                  )} />
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className={cn(
                          "w-14 h-14 rounded-2xl flex items-center justify-center shadow-lg",
                          symbol === 'BTC'
                            ? "bg-gradient-to-br from-yellow-500 to-orange-500"
                            : "bg-gradient-to-br from-blue-500 to-purple-500"
                        )}>
                          {symbol === 'BTC' ? <Bitcoin className="w-7 h-7 text-white" /> : <Layers className="w-7 h-7 text-white" />}
                        </div>
                        <div>
                          <CardTitle className="text-2xl">{symbol}-PERP</CardTitle>
                          <CardDescription className="text-lg tabular-nums">{formatCurrency(signal.price)}</CardDescription>
                        </div>
                      </div>
                      <SignalBadge action={signal.action} size="lg" />
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {/* Signal Details Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div className="p-4 rounded-xl bg-secondary/30 text-center">
                        <p className="text-xs text-muted-foreground mb-1">Regime</p>
                        <p className="font-bold capitalize">{signal.regime}</p>
                      </div>
                      <div className="p-4 rounded-xl bg-secondary/30 text-center">
                        <p className="text-xs text-muted-foreground mb-1">Confidence</p>
                        <p className="font-bold">{(() => {
                          const conf = signal.confidence || 0
                          return conf > 1 ? `${conf.toFixed(0)}%` : formatPercent(conf)
                        })()}</p>
                      </div>
                      <div className="p-4 rounded-xl bg-secondary/30 text-center">
                        <p className="text-xs text-muted-foreground mb-1">Strength</p>
                        <p className="font-bold">{signal.strength || '--'}</p>
                      </div>
                      <div className="p-4 rounded-xl bg-secondary/30 text-center">
                        <p className="text-xs text-muted-foreground mb-1">Strategy</p>
                        <p className="font-bold text-xs">{signal.strategy || '--'}</p>
                      </div>
                    </div>

                    {/* Stop/Target */}
                    <div className="grid grid-cols-2 gap-3">
                      <div className="p-4 rounded-xl bg-danger/10 border border-danger/20">
                        <div className="flex items-center gap-2 mb-2">
                          <ArrowDownRight className="w-4 h-4 text-danger" />
                          <span className="text-sm text-danger font-medium">Stop Loss</span>
                        </div>
                        <p className="text-xl font-bold text-danger tabular-nums">{formatCurrency(signal.stop_loss)}</p>
                        <p className="text-xs text-danger/70">
                          {signal.price && signal.stop_loss ? (() => {
                            const pct = ((signal.stop_loss - signal.price) / signal.price) * 100
                            return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`
                          })() : '--'}
                        </p>
                      </div>
                      <div className="p-4 rounded-xl bg-success/10 border border-success/20">
                        <div className="flex items-center gap-2 mb-2">
                          <ArrowUpRight className="w-4 h-4 text-success" />
                          <span className="text-sm text-success font-medium">Take Profit</span>
                        </div>
                        <p className="text-xl font-bold text-success tabular-nums">{formatCurrency(signal.take_profit)}</p>
                        <p className="text-xs text-success/70">
                          {signal.price && signal.take_profit ? (() => {
                            const pct = ((signal.take_profit - signal.price) / signal.price) * 100
                            return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`
                          })() : '--'}
                        </p>
                      </div>
                    </div>

                    {/* Reasons */}
                    <div>
                      <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                        <CheckCircle className="w-4 h-4 text-success" />
                        Signal Reasons
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {(signal.reasons || []).map((reason, i) => (
                          <Badge key={i} variant="outline" className="text-xs py-1">
                            {formatReason(reason)}
                          </Badge>
                        ))}
                        {(!signal.reasons || signal.reasons.length === 0) && (
                          <span className="text-sm text-muted-foreground">No specific reasons</span>
                        )}
                      </div>
                    </div>

                    {/* Traps */}
                    <div>
                      <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4 text-warning" />
                        Trap Detection
                      </h4>
                      {(signal.traps_detected || []).length > 0 ? (
                        <div className="space-y-2">
                          {signal.traps_detected.map((trap, i) => (
                            <div key={i} className="flex items-center gap-2 p-2 rounded-lg bg-warning/10 border border-warning/20">
                              <AlertCircle className="w-4 h-4 text-warning" />
                              <span className="text-sm text-warning">{formatTrap(trap)}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 p-3 rounded-lg bg-success/10">
                          <CheckCircle className="w-4 h-4 text-success" />
                          <span className="text-sm text-success">No traps detected</span>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
              {Object.keys(lastSignals).length === 0 && (
                <Card className="col-span-full glass-card">
                  <CardContent className="py-16 text-center">
                    <Zap className="w-16 h-16 mx-auto text-muted-foreground/30 mb-4" />
                    <p className="text-lg font-medium text-muted-foreground">No signals available</p>
                    <p className="text-sm text-muted-foreground mt-1">Waiting for next trading cycle</p>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* Trades Tab */}
          {activeTab === 'trades' && (
            <Card className="glass-card">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <Clock className="w-5 h-5" />
                      Trade History
                    </CardTitle>
                    <CardDescription>
                      Closed trades with P&L ({trades.length} total)
                    </CardDescription>
                  </div>
                  {trades.length > 0 && (
                    <div className={cn(
                      "text-right p-3 rounded-xl",
                      trades.reduce((sum, t) => sum + (t.pnl || 0), 0) >= 0 ? "bg-success/10" : "bg-danger/10"
                    )}>
                      <p className="text-xs text-muted-foreground">Total P&L</p>
                      <p className={cn(
                        "text-xl font-bold tabular-nums",
                        trades.reduce((sum, t) => sum + (t.pnl || 0), 0) >= 0 ? "text-success" : "text-danger"
                      )}>
                        {trades.reduce((sum, t) => sum + (t.pnl || 0), 0) >= 0 ? '+' : ''}
                        {formatCurrency(trades.reduce((sum, t) => sum + (t.pnl || 0), 0))}
                      </p>
                    </div>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left p-3 text-muted-foreground font-medium">Date</th>
                        <th className="text-left p-3 text-muted-foreground font-medium">Symbol</th>
                        <th className="text-left p-3 text-muted-foreground font-medium">Side</th>
                        <th className="text-left p-3 text-muted-foreground font-medium">Entry</th>
                        <th className="text-left p-3 text-muted-foreground font-medium">Exit</th>
                        <th className="text-left p-3 text-muted-foreground font-medium">Size</th>
                        <th className="text-left p-3 text-muted-foreground font-medium">P&L</th>
                        <th className="text-left p-3 text-muted-foreground font-medium">Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trades.slice().reverse().map((trade, i) => {
                        // Normalize trade fields for consistency
                        const tradeSymbol = trade.symbol || trade.asset || 'Unknown'
                        const tradeDirection = trade.direction || trade.action || 'HOLD'
                        const tradeEntryPrice = trade.entry_price || trade.price
                        const tradePnlPct = trade.pnl_pct !== undefined
                          ? (typeof trade.pnl_pct === 'number' ? trade.pnl_pct.toFixed(2) : trade.pnl_pct)
                          : null

                        return (
                          <tr key={i} className="border-b border-border/50 hover:bg-secondary/20 transition-colors">
                            <td className="p-3 text-muted-foreground text-xs">
                              <div>{trade.entry_time ? new Date(trade.entry_time).toLocaleDateString() : '--'}</div>
                              <div className="text-muted-foreground/70">{trade.exit_time ? new Date(trade.exit_time).toLocaleDateString() : 'Open'}</div>
                            </td>
                            <td className="p-3">
                              <div className="flex items-center gap-2">
                                <div className={cn(
                                  "w-6 h-6 rounded-lg flex items-center justify-center",
                                  tradeSymbol === 'BTC' ? "bg-yellow-500" : "bg-blue-500"
                                )}>
                                  {tradeSymbol === 'BTC' ? <Bitcoin className="w-3 h-3 text-white" /> : <Layers className="w-3 h-3 text-white" />}
                                </div>
                                <span className="font-medium">{tradeSymbol}</span>
                              </div>
                            </td>
                            <td className="p-3">
                              <SignalBadge action={tradeDirection} />
                            </td>
                            <td className="p-3 font-mono tabular-nums">{formatCurrency(tradeEntryPrice)}</td>
                            <td className="p-3 font-mono tabular-nums">{trade.exit_price ? formatCurrency(trade.exit_price) : '--'}</td>
                            <td className="p-3 font-mono tabular-nums">{formatCurrency(trade.value)}</td>
                            <td className="p-3">
                              <div className={cn(
                                "font-semibold tabular-nums",
                                (trade.pnl || 0) >= 0 ? "text-success" : "text-danger"
                              )}>
                                {(trade.pnl || 0) >= 0 ? '+' : ''}{formatCurrency(trade.pnl || 0)}
                              </div>
                              {tradePnlPct !== null && (
                                <div className={cn(
                                  "text-xs tabular-nums",
                                  parseFloat(tradePnlPct) >= 0 ? "text-success/70" : "text-danger/70"
                                )}>
                                  {parseFloat(tradePnlPct) >= 0 ? '+' : ''}{tradePnlPct}%
                                </div>
                              )}
                            </td>
                            <td className="p-3">
                              <Badge variant={
                                trade.exit_reason === 'take_profit' ? 'outline' :
                                trade.exit_reason === 'stop_loss' ? 'destructive' : 'secondary'
                              } className={cn(
                                "text-xs",
                                trade.exit_reason === 'take_profit' && "border-success text-success"
                              )}>
                                {trade.exit_reason === 'take_profit' ? 'TP Hit' :
                                 trade.exit_reason === 'stop_loss' ? 'SL Hit' :
                                 trade.exit_reason === 'opposite_signal' ? 'Signal' :
                                 trade.exit_reason || 'Open'}
                              </Badge>
                            </td>
                          </tr>
                        )
                      })}
                      {trades.length === 0 && (
                        <tr>
                          <td colSpan={8} className="p-12 text-center text-muted-foreground">
                            <Clock className="w-12 h-12 mx-auto mb-4 opacity-30" />
                            <p className="font-medium">No closed trades yet</p>
                            <p className="text-xs mt-1">Trades will appear here when positions are closed</p>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Analytics Tab */}
          {activeTab === 'analytics' && (
            <div className="space-y-6">
              {/* Performance Metrics */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <MetricCard
                  title="Profit Factor"
                  value={metrics.profit_factor ? parseFloat(metrics.profit_factor).toFixed(2) : (metrics.profitFactor ? parseFloat(metrics.profitFactor).toFixed(2) : '--')}
                  subtitle="Gross profit / Gross loss"
                  icon={BarChart3}
                  color="primary"
                />
                <MetricCard
                  title="Sharpe Ratio"
                  value={metrics.sharpeRatio || metrics.sharpe_ratio || '--'}
                  subtitle="Risk-adjusted return"
                  icon={Activity}
                  color="purple"
                />
                <MetricCard
                  title="Max Drawdown"
                  value={(() => {
                    const maxDD = metrics.maxDrawdown || metrics.max_drawdown
                    if (!maxDD) return '--'
                    const value = parseFloat(maxDD)
                    // Handle both 0-1 and 0-100 formats
                    return value > 1 ? `${value.toFixed(1)}%` : formatPercent(value)
                  })()}
                  subtitle="Largest peak to trough"
                  icon={TrendingDown}
                  color="danger"
                />
                <MetricCard
                  title="Avg Trade"
                  value={(() => {
                    const avgTrade = metrics.avgTrade || metrics.avg_trade || metrics.expectancy
                    if (!avgTrade) return '--'
                    return formatCurrency(parseFloat(avgTrade))
                  })()}
                  subtitle="Average P&L per trade"
                  icon={DollarSign}
                  color="success"
                />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Daily P&L Chart */}
                {dailyPnL.length > 0 && (
                  <Card className="glass-card">
                    <CardHeader>
                      <CardTitle className="text-base">Daily P&L</CardTitle>
                      <CardDescription>Profit and loss by day</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={dailyPnL}>
                            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                            <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={10} />
                            <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} tickFormatter={(v) => `$${v}`} />
                            <Tooltip content={<CustomTooltip />} />
                            <Bar dataKey="pnl" name="P&L" radius={[4, 4, 0, 0]}>
                              {dailyPnL.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={entry.pnl >= 0 ? COLORS.success : COLORS.danger} />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Regime Distribution */}
                {regimePieData.length > 0 && (
                  <Card className="glass-card">
                    <CardHeader>
                      <CardTitle className="text-base">Trades by Regime</CardTitle>
                      <CardDescription>Distribution across market conditions</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={regimePieData}
                              cx="50%"
                              cy="50%"
                              innerRadius={60}
                              outerRadius={100}
                              paddingAngle={2}
                              dataKey="value"
                            >
                              {regimePieData.map((entry, index) => (
                                <Cell
                                  key={`cell-${index}`}
                                  fill={
                                    entry.name === 'bull' ? COLORS.success :
                                    entry.name === 'bear' ? COLORS.danger :
                                    entry.name === 'sideways' ? COLORS.warning :
                                    COLORS.purple
                                  }
                                />
                              ))}
                            </Pie>
                            <Tooltip content={<CustomTooltip />} />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                      <div className="flex justify-center gap-4 mt-4 flex-wrap">
                        {regimePieData.map((entry, i) => (
                          <div key={i} className="flex items-center gap-2">
                            <div
                              className="w-3 h-3 rounded-full"
                              style={{
                                backgroundColor: entry.name === 'bull' ? COLORS.success :
                                entry.name === 'bear' ? COLORS.danger :
                                entry.name === 'sideways' ? COLORS.warning : COLORS.purple
                              }}
                            />
                            <span className="text-sm capitalize">{entry.name}: {entry.value}</span>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}
              </div>

              {/* Advanced Metrics */}
              <Card className="glass-card">
                <CardHeader>
                  <CardTitle className="text-base">Advanced Statistics</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                    <div className="p-4 rounded-xl bg-secondary/30">
                      <p className="text-xs text-muted-foreground">Total Trades</p>
                      <p className="text-xl font-bold">{trades.length}</p>
                    </div>
                    <div className="p-4 rounded-xl bg-secondary/30">
                      <p className="text-xs text-muted-foreground">Win Rate</p>
                      <p className="text-xl font-bold">
                        {(() => {
                          const closedTrades = trades.filter(t => t.pnl !== undefined && t.pnl !== null)
                          if (closedTrades.length === 0) return '--'
                          const winRate = (closedTrades.filter(t => t.pnl > 0).length / closedTrades.length) * 100
                          return `${winRate.toFixed(1)}%`
                        })()}
                      </p>
                    </div>
                    <div className="p-4 rounded-xl bg-success/10">
                      <p className="text-xs text-success">Avg Win</p>
                      <p className="text-xl font-bold text-success">
                        {(() => {
                          const winningTrades = trades.filter(t => t.pnl !== undefined && t.pnl > 0)
                          if (winningTrades.length === 0) return '--'
                          const avgWin = winningTrades.reduce((sum, t) => sum + t.pnl, 0) / winningTrades.length
                          return `+${formatCurrency(avgWin)}`
                        })()}
                      </p>
                    </div>
                    <div className="p-4 rounded-xl bg-danger/10">
                      <p className="text-xs text-danger">Avg Loss</p>
                      <p className="text-xl font-bold text-danger">
                        {(() => {
                          const losingTrades = trades.filter(t => t.pnl !== undefined && t.pnl < 0)
                          if (losingTrades.length === 0) return '--'
                          const avgLoss = losingTrades.reduce((sum, t) => sum + t.pnl, 0) / losingTrades.length
                          return formatCurrency(avgLoss)
                        })()}
                      </p>
                    </div>
                    <div className="p-4 rounded-xl bg-secondary/30">
                      <p className="text-xs text-muted-foreground">Longest Win Streak</p>
                      <p className="text-xl font-bold">
                        {(() => {
                          const closedTrades = trades.filter(t => t.pnl !== undefined && t.pnl !== null)
                          if (closedTrades.length === 0) return 0
                          let max = 0, current = 0
                          closedTrades.forEach(t => {
                            if (t.pnl > 0) { current++; max = Math.max(max, current) }
                            else { current = 0 }
                          })
                          return max
                        })()}
                      </p>
                    </div>
                    <div className="p-4 rounded-xl bg-secondary/30">
                      <p className="text-xs text-muted-foreground">Longest Loss Streak</p>
                      <p className="text-xl font-bold">
                        {(() => {
                          const closedTrades = trades.filter(t => t.pnl !== undefined && t.pnl !== null)
                          if (closedTrades.length === 0) return 0
                          let max = 0, current = 0
                          closedTrades.forEach(t => {
                            if (t.pnl < 0) { current++; max = Math.max(max, current) }
                            else { current = 0 }
                          })
                          return max
                        })()}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Decision Log */}
              <Card className="glass-card">
                <CardHeader>
                  <CardTitle className="text-base">Decision Log</CardTitle>
                  <CardDescription>Complete history of trading decisions</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {decisionLog.slice().reverse().map((entry, i) => (
                      <div key={i} className="p-4 rounded-xl bg-secondary/30 hover:bg-secondary/50 transition-colors">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-3">
                            <span className="text-xs text-muted-foreground">{formatDate(entry.timestamp)}</span>
                            <SignalBadge action={entry.action} />
                          </div>
                          <Badge variant="secondary">{entry.symbol}</Badge>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                          <div>
                            <span className="text-muted-foreground">Regime:</span>
                            <span className="ml-2 font-medium capitalize">{entry.regime || '--'}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Confidence:</span>
                            <span className="ml-2 font-medium">{(() => {
                              const conf = entry.confidence || 0
                              return conf > 1 ? `${conf.toFixed(0)}%` : formatPercent(conf)
                            })()}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Strength:</span>
                            <span className="ml-2 font-medium">{entry.strength || '--'}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Strategy:</span>
                            <span className="ml-2 font-medium text-xs">{entry.strategy || '--'}</span>
                          </div>
                        </div>
                        {entry.reasons?.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1">
                            {entry.reasons.map((reason, j) => (
                              <Badge key={j} variant="outline" className="text-xs">{formatReason(reason)}</Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                    {decisionLog.length === 0 && (
                      <p className="text-center text-muted-foreground py-8">No decisions logged yet</p>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </main>
      </div>

      {/* Footer */}
      <footer className="border-t glass-panel py-6 mt-auto">
        <div className="container mx-auto px-4">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary via-purple-500 to-pink-500 flex items-center justify-center">
                <BarChart3 className="w-4 h-4 text-white" />
              </div>
              <span className="text-sm font-medium">Trading Bot v3.2</span>
            </div>
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              <span className="flex items-center gap-1">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-success"></span>
                </span>
                Paper Trading
              </span>
              <span>•</span>
              <span>Updates every 4 hours</span>
              <span>•</span>
              <span>Drift Protocol</span>
            </div>
          </div>
        </div>
      </footer>

      {/* Global Styles */}
      <style>{`
        .glass-panel {
          background: hsl(var(--background) / 0.8);
          backdrop-filter: blur(12px);
        }

        .glass-card {
          background: hsl(var(--card) / 0.6);
          backdrop-filter: blur(12px);
          border: 1px solid hsl(var(--border) / 0.5);
        }

        @keyframes float {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-10px); }
        }

        .animate-float {
          animation: float 3s ease-in-out infinite;
        }

        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          25% { transform: translateX(-5px); }
          75% { transform: translateX(5px); }
        }

        .animate-shake {
          animation: shake 0.3s ease-in-out;
        }

        .tabular-nums {
          font-variant-numeric: tabular-nums;
        }
      `}</style>
    </div>
  )
}
