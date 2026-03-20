import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn, formatCurrency, formatPercent, formatDate, formatReason, formatTrap } from '@/lib/utils'
import {
  TrendingUp, TrendingDown, Minus, AlertTriangle, CheckCircle, XCircle,
  RefreshCw, DollarSign, Activity, Shield, BarChart3, Clock, Target,
  ArrowUpRight, ArrowDownRight, AlertCircle, Lock
} from 'lucide-react'

const API_BASE = '/api'

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState(null)
  const [lastUpdate, setLastUpdate] = useState(null)

  useEffect(() => {
    const token = sessionStorage.getItem('auth_token')
    if (token) {
      setIsAuthenticated(true)
      fetchData(token)
    }
  }, [])

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

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <div className="mx-auto mb-4 w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
              <Lock className="w-6 h-6" />
            </div>
            <CardTitle className="text-2xl">Trading Bot Dashboard</CardTitle>
            <CardDescription>Enter your password to access</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && authenticate()}
                placeholder="Password"
                className="w-full px-4 py-2 rounded-lg border bg-secondary text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <Button onClick={authenticate} className="w-full" disabled={loading}>
                {loading ? 'Authenticating...' : 'Enter Dashboard'}
              </Button>
              {error && <p className="text-center text-danger text-sm">{error}</p>}
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  const state = data?.state?.state || {}
  const lastSignals = state.last_signals || {}
  const trades = data?.history?.trades || state.paper_trades || []
  const metrics = data?.metrics?.metrics || {}
  const safetyStatus = data?.state?.safetyStatus || {}
  const decisionLog = data?.state?.decisions || state.decision_log || []

  // Pegar último sinal (BTC ou ETH)
  const lastSignal = lastSignals['BTC'] || lastSignals['ETH'] || {}

  const regime = state.last_regime || lastSignal.regime || 'unknown'
  const action = lastSignal.action || 'HOLD'
  const details = lastSignal

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BarChart3 className="w-8 h-8 text-primary" />
            <div>
              <h1 className="text-xl font-bold">Trading Bot</h1>
              <p className="text-xs text-muted-foreground">Paper Trading Mode</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-muted-foreground">
              {lastUpdate ? `Updated ${formatDate(lastUpdate)}` : '--'}
            </span>
            <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
              <RefreshCw className={cn("w-4 h-4 mr-2", loading && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-6 space-y-6">
        {/* Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Capital Card */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Capital</CardTitle>
              <DollarSign className="w-4 h-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{formatCurrency(state.capital || 500)}</div>
              <p className={cn(
                "text-xs mt-1",
                (state.total_pnl || 0) >= 0 ? "text-success" : "text-danger"
              )}>
                {(state.total_pnl || 0) >= 0 ? '+' : ''}{formatCurrency(state.total_pnl || 0)} PnL
              </p>
            </CardContent>
          </Card>

          {/* Regime Card */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Market Regime</CardTitle>
              <Activity className="w-4 h-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                <Badge variant={
                  regime === 'bull' ? 'success' :
                  regime === 'bear' ? 'danger' :
                  regime === 'correction' ? 'warning' : 'secondary'
                } className="text-lg px-3 py-1">
                  {regime.toUpperCase()}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                Last detected at {formatDate(state.last_run)}
              </p>
            </CardContent>
          </Card>

          {/* Current Signal Card */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Current Signal</CardTitle>
              {action === 'LONG' ? <TrendingUp className="w-4 h-4 text-success" /> :
               action === 'SHORT' ? <TrendingDown className="w-4 h-4 text-danger" /> :
               <Minus className="w-4 h-4 text-muted-foreground" />}
            </CardHeader>
            <CardContent>
              <div className={cn(
                "text-2xl font-bold",
                action === 'LONG' ? "text-success" :
                action === 'SHORT' ? "text-danger" : "text-muted-foreground"
              )}>
                {action}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Confidence: {formatPercent(details.signal_confidence || details.confidence || 0)}
              </p>
            </CardContent>
          </Card>

          {/* Safety Status Card */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Safety Status</CardTitle>
              <Shield className="w-4 h-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2">
                {safetyStatus.blocked ? (
                  <><XCircle className="w-5 h-5 text-danger" /><span className="text-danger font-bold">BLOCKED</span></>
                ) : safetyStatus.warnings?.length > 0 ? (
                  <><AlertTriangle className="w-5 h-5 text-warning" /><span className="text-warning font-bold">WARNING</span></>
                ) : (
                  <><CheckCircle className="w-5 h-5 text-success" /><span className="text-success font-bold">OK</span></>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Consecutive Losses: {state.consecutive_losses || state.risk_state?.consecutive_losses || 0}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Asset Signals Overview */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Object.entries(lastSignals).map(([symbol, signal]) => (
            <Card key={symbol}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">{symbol}</CardTitle>
                  <Badge variant={
                    signal.action === 'LONG' ? 'success' :
                    signal.action === 'SHORT' ? 'danger' :
                    signal.action === 'BLOCKED' ? 'warning' : 'secondary'
                  }>
                    {signal.action}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">Regime:</span>
                    <span className="ml-2 font-medium">{signal.regime?.toUpperCase()}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Confidence:</span>
                    <span className="ml-2 font-medium">{formatPercent(signal.confidence || 0)}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Price:</span>
                    <span className="ml-2 font-medium">{formatCurrency(signal.price)}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Strength:</span>
                    <span className="ml-2 font-medium">{signal.strength}</span>
                  </div>
                </div>
                {signal.traps_detected?.length > 0 && (
                  <div className="mt-2 flex items-center gap-2 text-warning text-sm">
                    <AlertTriangle className="w-4 h-4" />
                    <span>Traps: {signal.traps_detected.join(', ')}</span>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
          {Object.keys(lastSignals).length === 0 && (
            <Card className="md:col-span-2">
              <CardContent className="py-8 text-center text-muted-foreground">
                No signal data available yet. Wait for the next trading cycle.
              </CardContent>
            </Card>
          )}
        </div>

        {/* Signal Analysis */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Main Signal */}
          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle>Signal Details</CardTitle>
              <CardDescription>Latest signal analysis</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className={cn(
                "text-center py-6 rounded-lg",
                action === 'LONG' ? "bg-success/10" :
                action === 'SHORT' ? "bg-danger/10" : "bg-secondary"
              )}>
                <div className={cn(
                  "text-5xl font-bold mb-2",
                  action === 'LONG' ? "text-success" :
                  action === 'SHORT' ? "text-danger" : "text-muted-foreground"
                )}>
                  {action === 'LONG' ? <ArrowUpRight className="w-16 h-16 mx-auto" /> :
                   action === 'SHORT' ? <ArrowDownRight className="w-16 h-16 mx-auto" /> :
                   <Minus className="w-16 h-16 mx-auto" />}
                </div>
                <div className="text-2xl font-bold">{action}</div>
                <div className="text-sm text-muted-foreground mt-1">
                  {details.signal_strength || details.strength || '--'} Signal
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="p-3 rounded-lg bg-secondary">
                  <div className="text-muted-foreground">Entry</div>
                  <div className="font-semibold">{formatCurrency(details.price)}</div>
                </div>
                <div className="p-3 rounded-lg bg-secondary">
                  <div className="text-muted-foreground">Position</div>
                  <div className="font-semibold">{formatCurrency(details.sizing?.position_value)}</div>
                </div>
                <div className="p-3 rounded-lg bg-secondary">
                  <div className="text-muted-foreground text-danger">Stop Loss</div>
                  <div className="font-semibold text-danger">{formatCurrency(details.stop_loss)}</div>
                </div>
                <div className="p-3 rounded-lg bg-secondary">
                  <div className="text-muted-foreground text-success">Take Profit</div>
                  <div className="font-semibold text-success">{formatCurrency(details.take_profit)}</div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Decision Reasons */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CheckCircle className="w-5 h-5 text-success" />
                Decision Reasons
              </CardTitle>
              <CardDescription>Why this signal was generated</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {(details.signal_reasons || details.reasons || [])
                  .filter(r => !r.includes('BLOCKED') && !r.includes('trap'))
                  .map((reason, i) => (
                  <div key={i} className="flex items-center gap-2 p-2 rounded bg-secondary text-sm">
                    <CheckCircle className="w-4 h-4 text-success flex-shrink-0" />
                    <span>{formatReason(reason)}</span>
                  </div>
                ))}
                {(!details.signal_reasons?.length && !details.reasons?.length) && (
                  <p className="text-muted-foreground text-sm">No specific reasons available</p>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Trap Detection */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-warning" />
                Trap Detection
              </CardTitle>
              <CardDescription>Market manipulation warnings</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {(details.traps_detected || lastSignal.traps_detected || []).length > 0 ? (
                  (details.traps_detected || lastSignal.traps_detected || []).map((trap, i) => (
                    <div key={i} className="flex items-center gap-2 p-2 rounded bg-warning/10 text-sm">
                      <AlertCircle className="w-4 h-4 text-warning flex-shrink-0" />
                      <span className="text-warning">{formatTrap(trap)}</span>
                    </div>
                  ))
                ) : (
                  <div className="flex items-center gap-2 p-3 rounded bg-success/10 text-sm">
                    <CheckCircle className="w-4 h-4 text-success" />
                    <span className="text-success">No traps detected</span>
                  </div>
                )}
                {lastSignal.trap_warning && (
                  <p className="text-xs text-warning mt-2">
                    Signal confidence was reduced due to trap detection
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Trade History */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="w-5 h-5" />
              Trade History
            </CardTitle>
            <CardDescription>All paper trades executed</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="text-left p-3 text-muted-foreground font-medium">Time</th>
                    <th className="text-left p-3 text-muted-foreground font-medium">Symbol</th>
                    <th className="text-left p-3 text-muted-foreground font-medium">Direction</th>
                    <th className="text-left p-3 text-muted-foreground font-medium">Entry</th>
                    <th className="text-left p-3 text-muted-foreground font-medium">Stop</th>
                    <th className="text-left p-3 text-muted-foreground font-medium">Target</th>
                    <th className="text-left p-3 text-muted-foreground font-medium">Size</th>
                    <th className="text-left p-3 text-muted-foreground font-medium">Regime</th>
                    <th className="text-left p-3 text-muted-foreground font-medium">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.slice().reverse().map((trade, i) => (
                    <tr key={i} className="border-b hover:bg-secondary/50">
                      <td className="p-3 text-muted-foreground">{formatDate(trade.timestamp)}</td>
                      <td className="p-3 font-medium">{trade.symbol}</td>
                      <td className="p-3">
                        <Badge variant={trade.action?.includes('LONG') ? 'success' : 'danger'}>
                          {trade.action}
                        </Badge>
                      </td>
                      <td className="p-3">{formatCurrency(trade.price)}</td>
                      <td className="p-3 text-danger">{formatCurrency(trade.stop_loss)}</td>
                      <td className="p-3 text-success">{formatCurrency(trade.take_profit)}</td>
                      <td className="p-3">{formatCurrency(trade.value)}</td>
                      <td className="p-3">
                        <Badge variant="secondary">{trade.regime?.toUpperCase()}</Badge>
                      </td>
                      <td className="p-3">{formatPercent(trade.signal_confidence || 0)}</td>
                    </tr>
                  ))}
                  {trades.length === 0 && (
                    <tr>
                      <td colSpan={9} className="p-6 text-center text-muted-foreground">
                        No trades yet
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* Performance Metrics */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {[
            { label: 'Total Trades', value: trades.length || metrics.total_trades || 0, icon: Target },
            { label: 'Win Rate', value: metrics.win_rate ? formatPercent(metrics.win_rate) : '--', icon: TrendingUp },
            { label: 'Profit Factor', value: metrics.profit_factor?.toFixed(2) || '--', icon: BarChart3 },
            { label: 'Max Drawdown', value: metrics.max_drawdown ? formatPercent(metrics.max_drawdown) : '--', icon: TrendingDown },
            { label: 'Sharpe Ratio', value: metrics.sharpe_ratio?.toFixed(2) || '--', icon: Activity },
            { label: 'Avg Trade', value: formatCurrency(metrics.avg_trade) || '--', icon: DollarSign },
          ].map((metric, i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <div className="flex items-center gap-2 text-muted-foreground mb-1">
                  <metric.icon className="w-4 h-4" />
                  <span className="text-xs">{metric.label}</span>
                </div>
                <div className="text-xl font-bold">{metric.value}</div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Decision Log */}
        <Card>
          <CardHeader>
            <CardTitle>Decision Log</CardTitle>
            <CardDescription>Recent trading decisions and analysis</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {decisionLog.slice().reverse().map((entry, i) => (
                <div key={i} className="p-3 rounded-lg bg-secondary">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-muted-foreground">{formatDate(entry.timestamp)}</span>
                    <Badge variant={
                      entry.action === 'LONG' ? 'success' :
                      entry.action === 'SHORT' ? 'danger' :
                      entry.action === 'BLOCKED' ? 'warning' : 'secondary'
                    }>
                      {entry.symbol}: {entry.action}
                    </Badge>
                  </div>
                  <div className="text-sm">
                    <span className="text-muted-foreground">Regime: </span>{entry.regime || '--'}
                    <span className="mx-2">|</span>
                    <span className="text-muted-foreground">Confidence: </span>{formatPercent(entry.confidence || 0)}
                  </div>
                  {entry.reasons?.length > 0 && (
                    <div className="text-xs text-muted-foreground mt-1">
                      {entry.reasons.slice(0, 3).join(' • ')}
                    </div>
                  )}
                </div>
              ))}
              {decisionLog.length === 0 && (
                <p className="text-center text-muted-foreground py-6">No decisions logged yet</p>
              )}
            </div>
          </CardContent>
        </Card>
      </main>

      {/* Footer */}
      <footer className="border-t py-4 mt-8">
        <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
          Trading Bot v1.0 | Paper Trading Mode | Updates every 4 hours
        </div>
      </footer>
    </div>
  )
}
