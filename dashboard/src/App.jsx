import { useState, useEffect, useCallback } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn, formatCurrency, formatPercent, formatDate, formatReason, formatTrap } from '@/lib/utils'
import {
  LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, BarChart, Bar
} from 'recharts'
import {
  TrendingUp, TrendingDown, Minus, AlertTriangle, CheckCircle, XCircle,
  RefreshCw, DollarSign, Activity, Shield, BarChart3, Clock, Target,
  ArrowUpRight, ArrowDownRight, AlertCircle, Lock, Zap, Eye, EyeOff,
  Wallet, PieChart as PieChartIcon, Settings, Bell, Moon, Sun, Menu, X,
  Bitcoin, Layers, Brain, TrendingUp as TrendUp, ChevronRight, ExternalLink
} from 'lucide-react'

const API_BASE = '/api'

// Color constants
const COLORS = {
  success: '#22c55e',
  danger: '#ef4444',
  warning: '#f59e0b',
  primary: '#3b82f6',
  purple: '#8b5cf6',
  cyan: '#06b6d4',
}

// Custom tooltip for charts
const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-card/95 backdrop-blur-sm border border-border rounded-lg p-3 shadow-xl">
        <p className="text-xs text-muted-foreground mb-1">{label}</p>
        {payload.map((entry, index) => (
          <p key={index} className="text-sm font-semibold" style={{ color: entry.color }}>
            {entry.name}: {typeof entry.value === 'number' ? formatCurrency(entry.value) : entry.value}
          </p>
        ))}
      </div>
    )
  }
  return null
}

// Metric Card Component
const MetricCard = ({ title, value, subtitle, icon: Icon, trend, trendValue, color = 'primary', className }) => (
  <Card className={cn("relative overflow-hidden group hover:shadow-lg transition-all duration-300", className)}>
    <div className={cn(
      "absolute inset-0 opacity-5 group-hover:opacity-10 transition-opacity",
      `bg-gradient-to-br from-${color} to-transparent`
    )} />
    <CardContent className="p-4 relative">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{title}</p>
          <p className="text-2xl font-bold mt-1">{value}</p>
          {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
          {trend !== undefined && (
            <div className={cn(
              "flex items-center gap-1 mt-2 text-xs font-medium",
              trend >= 0 ? "text-success" : "text-danger"
            )}>
              {trend >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
              <span>{trend >= 0 ? '+' : ''}{trendValue}</span>
            </div>
          )}
        </div>
        <div className={cn(
          "w-10 h-10 rounded-xl flex items-center justify-center",
          color === 'success' ? "bg-success/10" :
          color === 'danger' ? "bg-danger/10" :
          color === 'warning' ? "bg-warning/10" :
          "bg-primary/10"
        )}>
          <Icon className={cn(
            "w-5 h-5",
            color === 'success' ? "text-success" :
            color === 'danger' ? "text-danger" :
            color === 'warning' ? "text-warning" :
            "text-primary"
          )} />
        </div>
      </div>
    </CardContent>
  </Card>
)

// Signal Badge Component
const SignalBadge = ({ action, size = 'default' }) => {
  const config = {
    'LONG': { color: 'success', icon: TrendingUp },
    'SHORT': { color: 'danger', icon: TrendingDown },
    'HOLD': { color: 'secondary', icon: Minus },
    'BLOCKED': { color: 'warning', icon: AlertTriangle },
  }
  const { color, icon: Icon } = config[action] || config['HOLD']

  return (
    <Badge variant={color} className={cn(
      "flex items-center gap-1",
      size === 'lg' && "text-lg px-4 py-2"
    )}>
      <Icon className={cn("w-3 h-3", size === 'lg' && "w-4 h-4")} />
      {action}
    </Badge>
  )
}

// Live Price Component
const LivePrice = ({ symbol, price, change }) => (
  <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-secondary/50">
    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-yellow-500 to-orange-500 flex items-center justify-center">
      {symbol === 'BTC' ? <Bitcoin className="w-4 h-4 text-white" /> : <Layers className="w-4 h-4 text-white" />}
    </div>
    <div>
      <p className="text-sm font-semibold">{symbol}</p>
      <p className="text-xs text-muted-foreground">{formatCurrency(price)}</p>
    </div>
    {change !== undefined && (
      <span className={cn(
        "text-xs font-medium ml-auto",
        change >= 0 ? "text-success" : "text-danger"
      )}>
        {change >= 0 ? '+' : ''}{change.toFixed(2)}%
      </span>
    )}
  </div>
)

// Asset Signal Card
const AssetSignalCard = ({ symbol, signal }) => {
  if (!signal) return null

  return (
    <Card className="overflow-hidden">
      <div className={cn(
        "h-1",
        signal.action === 'LONG' ? "bg-success" :
        signal.action === 'SHORT' ? "bg-danger" :
        "bg-muted"
      )} />
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={cn(
              "w-10 h-10 rounded-xl flex items-center justify-center",
              symbol === 'BTC' ? "bg-gradient-to-br from-yellow-500 to-orange-500" : "bg-gradient-to-br from-blue-500 to-purple-500"
            )}>
              {symbol === 'BTC' ? <Bitcoin className="w-5 h-5 text-white" /> : <Layers className="w-5 h-5 text-white" />}
            </div>
            <div>
              <CardTitle className="text-lg">{symbol}-PERP</CardTitle>
              <CardDescription>{formatCurrency(signal.price)}</CardDescription>
            </div>
          </div>
          <SignalBadge action={signal.action} />
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-3 mt-2">
          <div className="p-3 rounded-lg bg-secondary/50">
            <p className="text-xs text-muted-foreground">Regime</p>
            <p className="font-semibold capitalize">{signal.regime}</p>
          </div>
          <div className="p-3 rounded-lg bg-secondary/50">
            <p className="text-xs text-muted-foreground">Confidence</p>
            <p className="font-semibold">{formatPercent(signal.confidence || 0)}</p>
          </div>
          <div className="p-3 rounded-lg bg-danger/10">
            <p className="text-xs text-danger">Stop Loss</p>
            <p className="font-semibold text-danger">{formatCurrency(signal.stop_loss)}</p>
          </div>
          <div className="p-3 rounded-lg bg-success/10">
            <p className="text-xs text-success">Take Profit</p>
            <p className="font-semibold text-success">{formatCurrency(signal.take_profit)}</p>
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

// Main App Component
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
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-primary/10 via-transparent to-transparent" />

        <Card className="w-full max-w-md relative overflow-hidden border-primary/20">
          <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent" />

          <CardHeader className="text-center relative">
            <div className="mx-auto mb-4 w-16 h-16 rounded-2xl bg-gradient-to-br from-primary to-purple-500 flex items-center justify-center shadow-lg shadow-primary/25">
              <BarChart3 className="w-8 h-8 text-white" />
            </div>
            <CardTitle className="text-2xl font-bold bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text">
              Trading Bot
            </CardTitle>
            <CardDescription className="text-muted-foreground">
              Enter your password to access the dashboard
            </CardDescription>
          </CardHeader>

          <CardContent className="relative">
            <div className="space-y-4">
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && authenticate()}
                  placeholder="Password"
                  className="w-full pl-10 pr-10 py-3 rounded-xl border bg-secondary/50 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
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
                className="w-full py-6 bg-gradient-to-r from-primary to-purple-500 hover:from-primary/90 hover:to-purple-500/90 shadow-lg shadow-primary/25"
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
                <div className="flex items-center gap-2 p-3 rounded-lg bg-danger/10 border border-danger/20">
                  <AlertCircle className="w-4 h-4 text-danger" />
                  <p className="text-sm text-danger">{error}</p>
                </div>
              )}
            </div>

            <div className="mt-6 pt-6 border-t border-border/50">
              <p className="text-xs text-center text-muted-foreground">
                Protected access • Updates every 4 hours
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Extract data
  const state = data?.state?.state || {}
  const lastSignals = state.last_signals || {}
  const trades = data?.history?.trades || state.paper_trades || []
  const metrics = data?.metrics?.metrics || {}
  const safetyStatus = data?.state?.safetyStatus || {}
  const decisionLog = data?.state?.decisions || state.decision_log || []

  // Calculate equity curve from trades
  const equityCurve = trades.reduce((acc, trade, i) => {
    const prevEquity = acc.length > 0 ? acc[acc.length - 1].equity : 500
    const pnl = trade.pnl || 0
    acc.push({
      date: new Date(trade.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      equity: prevEquity + pnl,
      pnl
    })
    return acc
  }, [{ date: 'Start', equity: 500, pnl: 0 }])

  // Regime distribution
  const regimeData = trades.reduce((acc, trade) => {
    const regime = trade.regime || 'unknown'
    acc[regime] = (acc[regime] || 0) + 1
    return acc
  }, {})
  const regimePieData = Object.entries(regimeData).map(([name, value]) => ({ name, value }))

  // Direction distribution
  const directionData = trades.reduce((acc, trade) => {
    const action = trade.action || 'HOLD'
    acc[action] = (acc[action] || 0) + 1
    return acc
  }, {})

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b bg-background/80 backdrop-blur-xl">
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
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-purple-500 flex items-center justify-center shadow-lg shadow-primary/25">
                  <BarChart3 className="w-5 h-5 text-white" />
                </div>
                <div className="hidden sm:block">
                  <h1 className="text-lg font-bold">Trading Bot</h1>
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
                    <span className="text-xs text-muted-foreground">Paper Trading</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Live Prices */}
            <div className="hidden md:flex items-center gap-2">
              {Object.entries(lastSignals).map(([symbol, signal]) => (
                <LivePrice
                  key={symbol}
                  symbol={symbol}
                  price={signal.price}
                  change={signal.price_change_24h}
                />
              ))}
            </div>

            <div className="flex items-center gap-2">
              <span className="hidden sm:block text-xs text-muted-foreground">
                {lastUpdate ? `Updated ${formatDate(lastUpdate)}` : '--'}
              </span>
              <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
                <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
              </Button>
              <Button variant="ghost" size="sm" onClick={logout}>
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
            <div className="absolute inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />
            <nav className="absolute left-0 top-0 bottom-0 w-64 bg-card border-r p-4 space-y-2">
              {['overview', 'signals', 'trades', 'analytics'].map((tab) => (
                <button
                  key={tab}
                  onClick={() => { setActiveTab(tab); setSidebarOpen(false) }}
                  className={cn(
                    "w-full flex items-center gap-3 px-4 py-3 rounded-lg text-left transition-colors",
                    activeTab === tab ? "bg-primary/10 text-primary" : "hover:bg-secondary"
                  )}
                >
                  {tab === 'overview' && <Activity className="w-4 h-4" />}
                  {tab === 'signals' && <Zap className="w-4 h-4" />}
                  {tab === 'trades' && <Clock className="w-4 h-4" />}
                  {tab === 'analytics' && <PieChartIcon className="w-4 h-4" />}
                  <span className="capitalize">{tab}</span>
                </button>
              ))}
            </nav>
          </div>
        )}

        {/* Sidebar - Desktop */}
        <nav className="hidden lg:flex flex-col w-64 border-r bg-card/50 p-4 space-y-2 sticky top-[73px] h-[calc(100vh-73px)]">
          {['overview', 'signals', 'trades', 'analytics'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 rounded-lg text-left transition-all",
                activeTab === tab
                  ? "bg-gradient-to-r from-primary/20 to-purple-500/10 text-primary border-l-2 border-primary"
                  : "hover:bg-secondary"
              )}
            >
              {tab === 'overview' && <Activity className="w-4 h-4" />}
              {tab === 'signals' && <Zap className="w-4 h-4" />}
              {tab === 'trades' && <Clock className="w-4 h-4" />}
              {tab === 'analytics' && <PieChartIcon className="w-4 h-4" />}
              <span className="capitalize">{tab}</span>
              <ChevronRight className={cn("w-4 h-4 ml-auto transition-transform", activeTab === tab && "rotate-90")} />
            </button>
          ))}

          <div className="flex-1" />

          {/* Safety Status in Sidebar */}
          <Card className="bg-secondary/30">
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
                Losses: {state.consecutive_losses || 0}/3
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
                  title="Capital"
                  value={formatCurrency(state.capital || 500)}
                  subtitle={`Peak: ${formatCurrency(state.risk_state?.peak || 500)}`}
                  icon={Wallet}
                  trend={(state.total_pnl || 0) >= 0 ? 1 : -1}
                  trendValue={formatCurrency(state.total_pnl || 0)}
                  color={(state.total_pnl || 0) >= 0 ? 'success' : 'danger'}
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
                  title="Total Trades"
                  value={trades.length || state.total_trades || 0}
                  subtitle="Paper trades executed"
                  icon={Target}
                  color="primary"
                />
                <MetricCard
                  title="Win Rate"
                  value={metrics.win_rate ? formatPercent(metrics.win_rate) : '--'}
                  subtitle="Profitable trades"
                  icon={TrendUp}
                  color="success"
                />
              </div>

              {/* Asset Signals */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {Object.entries(lastSignals).map(([symbol, signal]) => (
                  <AssetSignalCard key={symbol} symbol={symbol} signal={signal} />
                ))}
                {Object.keys(lastSignals).length === 0 && (
                  <Card className="md:col-span-2">
                    <CardContent className="py-12 text-center">
                      <Activity className="w-12 h-12 mx-auto text-muted-foreground/50 mb-4" />
                      <p className="text-muted-foreground">No signal data available yet</p>
                      <p className="text-xs text-muted-foreground mt-1">Wait for the next trading cycle</p>
                    </CardContent>
                  </Card>
                )}
              </div>

              {/* Equity Chart */}
              {equityCurve.length > 1 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <TrendingUp className="w-5 h-5 text-primary" />
                      Equity Curve
                    </CardTitle>
                    <CardDescription>Portfolio value over time</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={equityCurve}>
                          <defs>
                            <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor={COLORS.primary} stopOpacity={0.3}/>
                              <stop offset="95%" stopColor={COLORS.primary} stopOpacity={0}/>
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                          <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                          <YAxis stroke="hsl(var(--muted-foreground))" fontSize={12} tickFormatter={(v) => `$${v}`} />
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

              {/* Recent Activity */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Clock className="w-5 h-5" />
                    Recent Decisions
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {decisionLog.slice(-5).reverse().map((entry, i) => (
                      <div key={i} className="flex items-center gap-4 p-3 rounded-lg bg-secondary/50 hover:bg-secondary/80 transition-colors">
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
                          <p>{formatPercent(entry.confidence || 0)}</p>
                          <p>{new Date(entry.timestamp).toLocaleTimeString()}</p>
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

          {/* Signals Tab */}
          {activeTab === 'signals' && (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {Object.entries(lastSignals).map(([symbol, signal]) => (
                  <Card key={symbol} className="overflow-hidden">
                    <div className={cn(
                      "h-2",
                      signal.action === 'LONG' ? "bg-gradient-to-r from-success to-emerald-400" :
                      signal.action === 'SHORT' ? "bg-gradient-to-r from-danger to-red-400" :
                      "bg-gradient-to-r from-muted to-muted-foreground/20"
                    )} />
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                          <div className={cn(
                            "w-14 h-14 rounded-2xl flex items-center justify-center",
                            symbol === 'BTC'
                              ? "bg-gradient-to-br from-yellow-500 to-orange-500"
                              : "bg-gradient-to-br from-blue-500 to-purple-500"
                          )}>
                            {symbol === 'BTC' ? <Bitcoin className="w-7 h-7 text-white" /> : <Layers className="w-7 h-7 text-white" />}
                          </div>
                          <div>
                            <CardTitle className="text-2xl">{symbol}-PERP</CardTitle>
                            <CardDescription className="text-lg">{formatCurrency(signal.price)}</CardDescription>
                          </div>
                        </div>
                        <SignalBadge action={signal.action} size="lg" />
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {/* Signal Details Grid */}
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="p-4 rounded-xl bg-secondary/50 text-center">
                          <p className="text-xs text-muted-foreground mb-1">Regime</p>
                          <p className="font-bold capitalize">{signal.regime}</p>
                        </div>
                        <div className="p-4 rounded-xl bg-secondary/50 text-center">
                          <p className="text-xs text-muted-foreground mb-1">Confidence</p>
                          <p className="font-bold">{formatPercent(signal.confidence || 0)}</p>
                        </div>
                        <div className="p-4 rounded-xl bg-secondary/50 text-center">
                          <p className="text-xs text-muted-foreground mb-1">Strength</p>
                          <p className="font-bold">{signal.strength || '--'}</p>
                        </div>
                        <div className="p-4 rounded-xl bg-secondary/50 text-center">
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
                          <p className="text-xl font-bold text-danger">{formatCurrency(signal.stop_loss)}</p>
                          <p className="text-xs text-danger/70">
                            {signal.price && signal.stop_loss ?
                              `${(((signal.stop_loss - signal.price) / signal.price) * 100).toFixed(2)}%` : '--'}
                          </p>
                        </div>
                        <div className="p-4 rounded-xl bg-success/10 border border-success/20">
                          <div className="flex items-center gap-2 mb-2">
                            <ArrowUpRight className="w-4 h-4 text-success" />
                            <span className="text-sm text-success font-medium">Take Profit</span>
                          </div>
                          <p className="text-xl font-bold text-success">{formatCurrency(signal.take_profit)}</p>
                          <p className="text-xs text-success/70">
                            {signal.price && signal.take_profit ?
                              `${(((signal.take_profit - signal.price) / signal.price) * 100).toFixed(2)}%` : '--'}
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
              </div>
            </>
          )}

          {/* Trades Tab */}
          {activeTab === 'trades' && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Clock className="w-5 h-5" />
                  Trade History
                </CardTitle>
                <CardDescription>All paper trades executed ({trades.length} total)</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left p-4 text-muted-foreground font-medium">Time</th>
                        <th className="text-left p-4 text-muted-foreground font-medium">Symbol</th>
                        <th className="text-left p-4 text-muted-foreground font-medium">Direction</th>
                        <th className="text-left p-4 text-muted-foreground font-medium">Entry</th>
                        <th className="text-left p-4 text-muted-foreground font-medium">Stop</th>
                        <th className="text-left p-4 text-muted-foreground font-medium">Target</th>
                        <th className="text-left p-4 text-muted-foreground font-medium">Size</th>
                        <th className="text-left p-4 text-muted-foreground font-medium">Regime</th>
                        <th className="text-left p-4 text-muted-foreground font-medium">Confidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trades.slice().reverse().map((trade, i) => (
                        <tr key={i} className="border-b border-border/50 hover:bg-secondary/30 transition-colors">
                          <td className="p-4 text-muted-foreground">
                            {new Date(trade.timestamp).toLocaleDateString()}<br/>
                            <span className="text-xs">{new Date(trade.timestamp).toLocaleTimeString()}</span>
                          </td>
                          <td className="p-4">
                            <div className="flex items-center gap-2">
                              <div className={cn(
                                "w-6 h-6 rounded-full flex items-center justify-center",
                                trade.symbol === 'BTC' ? "bg-yellow-500" : "bg-blue-500"
                              )}>
                                {trade.symbol === 'BTC' ? <Bitcoin className="w-3 h-3 text-white" /> : <Layers className="w-3 h-3 text-white" />}
                              </div>
                              <span className="font-medium">{trade.symbol}</span>
                            </div>
                          </td>
                          <td className="p-4">
                            <SignalBadge action={trade.action} />
                          </td>
                          <td className="p-4 font-mono">{formatCurrency(trade.price)}</td>
                          <td className="p-4 font-mono text-danger">{formatCurrency(trade.stop_loss)}</td>
                          <td className="p-4 font-mono text-success">{formatCurrency(trade.take_profit)}</td>
                          <td className="p-4 font-mono">{formatCurrency(trade.value)}</td>
                          <td className="p-4">
                            <Badge variant="secondary" className="capitalize">{trade.regime}</Badge>
                          </td>
                          <td className="p-4">{formatPercent(trade.signal_confidence || 0)}</td>
                        </tr>
                      ))}
                      {trades.length === 0 && (
                        <tr>
                          <td colSpan={9} className="p-12 text-center text-muted-foreground">
                            <Clock className="w-12 h-12 mx-auto mb-4 opacity-50" />
                            <p>No trades executed yet</p>
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
                  value={metrics.profit_factor?.toFixed(2) || '--'}
                  subtitle="Gross profit / Gross loss"
                  icon={BarChart3}
                  color="primary"
                />
                <MetricCard
                  title="Sharpe Ratio"
                  value={metrics.sharpe_ratio?.toFixed(2) || '--'}
                  subtitle="Risk-adjusted return"
                  icon={Activity}
                  color="purple"
                />
                <MetricCard
                  title="Max Drawdown"
                  value={metrics.max_drawdown ? formatPercent(metrics.max_drawdown) : '--'}
                  subtitle="Largest peak to trough"
                  icon={TrendingDown}
                  color="danger"
                />
                <MetricCard
                  title="Avg Trade"
                  value={metrics.avg_trade ? formatCurrency(metrics.avg_trade) : '--'}
                  subtitle="Average P&L per trade"
                  icon={DollarSign}
                  color="success"
                />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Regime Distribution */}
                {regimePieData.length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle>Trades by Regime</CardTitle>
                      <CardDescription>Distribution of trades across market regimes</CardDescription>
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
                      <div className="flex justify-center gap-4 mt-4">
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

                {/* Direction Distribution */}
                <Card>
                  <CardHeader>
                    <CardTitle>Trade Directions</CardTitle>
                    <CardDescription>Long vs Short distribution</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="h-64">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={Object.entries(directionData).map(([name, value]) => ({ name, value }))}>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                          <XAxis dataKey="name" stroke="hsl(var(--muted-foreground))" />
                          <YAxis stroke="hsl(var(--muted-foreground))" />
                          <Tooltip content={<CustomTooltip />} />
                          <Bar dataKey="value" fill={COLORS.primary} radius={[4, 4, 0, 0]}>
                            {Object.entries(directionData).map(([name], index) => (
                              <Cell
                                key={`cell-${index}`}
                                fill={name.includes('LONG') ? COLORS.success : name.includes('SHORT') ? COLORS.danger : COLORS.primary}
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Decision Log */}
              <Card>
                <CardHeader>
                  <CardTitle>Full Decision Log</CardTitle>
                  <CardDescription>Complete history of trading decisions</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {decisionLog.slice().reverse().map((entry, i) => (
                      <div key={i} className="p-4 rounded-lg bg-secondary/50 hover:bg-secondary/80 transition-colors">
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
                            <span className="ml-2 font-medium">{formatPercent(entry.confidence || 0)}</span>
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
      <footer className="border-t py-6 mt-auto">
        <div className="container mx-auto px-4">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-purple-500 flex items-center justify-center">
                <BarChart3 className="w-4 h-4 text-white" />
              </div>
              <span className="text-sm font-medium">Trading Bot v2.0</span>
            </div>
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
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
    </div>
  )
}
