"""
Telegram Notifications Module

Envia notificações formatadas para Telegram.
Suporta diferentes tipos de mensagem com formatação apropriada.

Uso:
    from src.notifications import TelegramNotifier

    notifier = TelegramNotifier()  # Usa env vars

    # Notificação de trade
    notifier.send_trade_signal(symbol="BTC", action="BUY", ...)

    # Status do bot
    notifier.send_status(capital=500, pnl=25, ...)

    # Erro
    notifier.send_error("Conexão perdida")
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TelegramConfig:
    """Configuração do Telegram."""
    bot_token: str = ""
    chat_id: str = ""
    enabled: bool = True
    silent_hours: tuple = (23, 7)  # Não notificar entre 23h e 7h

    @classmethod
    def from_env(cls) -> "TelegramConfig":
        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            enabled=os.getenv("TELEGRAM_ENABLED", "true").lower() == "true",
        )

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)


class TelegramNotifier:
    """
    Envia notificações para Telegram.

    Tipos de mensagem:
    - Trade signals (BUY/SELL/HOLD)
    - Status updates
    - Error alerts
    - Daily summaries
    """

    def __init__(self, config: TelegramConfig = None):
        self.config = config or TelegramConfig.from_env()
        self._api_url = f"https://api.telegram.org/bot{self.config.bot_token}"

    def is_configured(self) -> bool:
        """Verifica se Telegram está configurado."""
        return self.config.is_configured()

    def _send_message(
        self,
        text: str,
        parse_mode: str = "Markdown",
        disable_notification: bool = False
    ) -> bool:
        """Envia mensagem para o chat configurado."""
        if not self.is_configured():
            logger.debug("Telegram not configured, skipping notification")
            return False

        if not self.config.enabled:
            logger.debug("Telegram disabled, skipping notification")
            return False

        try:
            import requests

            response = requests.post(
                f"{self._api_url}/sendMessage",
                data={
                    "chat_id": self.config.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_notification": disable_notification,
                },
                timeout=10
            )

            if response.status_code == 200:
                logger.debug("Telegram message sent")
                return True
            else:
                logger.warning(f"Telegram API error: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    def send_trade_signal(
        self,
        symbol: str,
        action: str,
        regime: str,
        strategy: str,
        confidence: float,
        price: float = None,
        stop_loss: float = None,
        take_profit: float = None,
        position_size: float = None,
        executed: bool = False,
        mode: str = "paper"
    ) -> bool:
        """
        Envia notificação de sinal de trade.

        Args:
            symbol: Par de trading (BTC, ETH)
            action: BUY, SELL, ou HOLD
            regime: Regime de mercado detectado
            strategy: Estratégia selecionada
            confidence: Confiança do modelo (0-1)
            price: Preço atual
            stop_loss: Preço do stop loss
            take_profit: Preço do take profit
            position_size: Tamanho da posição em $
            executed: Se o trade foi executado
            mode: paper, live, backtest
        """
        # Emoji por ação
        action_emoji = {
            "BUY": "🟢",
            "SELL": "🔴",
            "HOLD": "⏸️",
            "BLOCKED": "🚫",
            "SKIP": "⏭️"
        }.get(action, "❓")

        # Emoji por regime
        regime_emoji = {
            "BULL": "🐂",
            "BEAR": "🐻",
            "SIDEWAYS": "➡️",
            "CORRECTION": "📉"
        }.get(regime, "")

        # Construir mensagem
        lines = [
            f"{action_emoji} *{action}* {symbol}",
            "",
            f"📊 Regime: {regime} {regime_emoji}",
            f"🎯 Estratégia: `{strategy}`",
            f"💪 Confiança: `{confidence:.0%}`",
        ]

        if price:
            lines.append(f"💰 Preço: `${price:,.2f}`")

        if stop_loss and action in ["BUY", "SELL"]:
            risk_pct = abs(price - stop_loss) / price * 100 if price else 0
            lines.append(f"🛑 Stop Loss: `${stop_loss:,.2f}` ({risk_pct:.1f}%)")

        if take_profit:
            lines.append(f"🎯 Take Profit: `${take_profit:,.2f}`")

        if position_size and action in ["BUY", "SELL"]:
            lines.append(f"📐 Posição: `${position_size:,.2f}`")

        lines.append("")

        if executed:
            lines.append("✅ *Trade executado*")
        else:
            lines.append("📝 *Sinal gerado* (não executado)")

        lines.append(f"_Modo: {mode}_")
        lines.append(f"_Horário: {datetime.now().strftime('%H:%M:%S')}_")

        message = "\n".join(lines)
        return self._send_message(message)

    def send_status(
        self,
        capital: float,
        initial_capital: float = 500.0,
        total_pnl: float = 0.0,
        daily_pnl: float = 0.0,
        open_positions: int = 0,
        total_trades: int = 0,
        win_rate: float = None,
        current_regime: str = None,
        last_trade: str = None,
        mode: str = "paper"
    ) -> bool:
        """
        Envia status atual do bot.

        Chamado via comando /status ou periodicamente.
        """
        # Calcular variação
        pnl_pct = (capital - initial_capital) / initial_capital * 100

        # Emoji baseado no PnL
        if pnl_pct > 5:
            status_emoji = "🚀"
        elif pnl_pct > 0:
            status_emoji = "📈"
        elif pnl_pct > -5:
            status_emoji = "📉"
        else:
            status_emoji = "💀"

        lines = [
            f"{status_emoji} *Status do Bot*",
            "",
            f"💰 Capital: `${capital:,.2f}`",
            f"📊 PnL Total: `${total_pnl:+,.2f}` ({pnl_pct:+.1f}%)",
            f"📅 PnL Hoje: `${daily_pnl:+,.2f}`",
            "",
            f"📈 Trades: `{total_trades}`",
        ]

        if win_rate is not None:
            lines.append(f"🎯 Win Rate: `{win_rate:.1%}`")

        if open_positions > 0:
            lines.append(f"📂 Posições Abertas: `{open_positions}`")

        if current_regime:
            regime_emoji = {
                "BULL": "🐂",
                "BEAR": "🐻",
                "SIDEWAYS": "➡️",
                "CORRECTION": "📉"
            }.get(current_regime, "")
            lines.append(f"🌡️ Regime: `{current_regime}` {regime_emoji}")

        if last_trade:
            lines.append(f"⏰ Último trade: `{last_trade}`")

        lines.append("")
        lines.append(f"_Modo: {mode}_")
        lines.append(f"_Atualizado: {datetime.now().strftime('%d/%m %H:%M')}_")

        message = "\n".join(lines)
        return self._send_message(message)

    def send_daily_summary(
        self,
        date: str,
        capital: float,
        daily_pnl: float,
        trades_count: int,
        wins: int,
        losses: int,
        best_trade: float = None,
        worst_trade: float = None,
        regime_changes: int = 0
    ) -> bool:
        """
        Envia resumo diário.

        Chamado no final do dia ou início do próximo.
        """
        win_rate = wins / trades_count if trades_count > 0 else 0

        # Emoji baseado no resultado
        if daily_pnl > 0:
            day_emoji = "✅"
        elif daily_pnl == 0:
            day_emoji = "➖"
        else:
            day_emoji = "❌"

        lines = [
            f"📅 *Resumo do Dia* - {date}",
            "",
            f"{day_emoji} PnL: `${daily_pnl:+,.2f}`",
            f"💰 Capital: `${capital:,.2f}`",
            "",
            f"📊 Trades: `{trades_count}`",
            f"✅ Wins: `{wins}` | ❌ Losses: `{losses}`",
            f"🎯 Win Rate: `{win_rate:.0%}`",
        ]

        if best_trade is not None:
            lines.append(f"🏆 Melhor: `${best_trade:+,.2f}`")

        if worst_trade is not None:
            lines.append(f"💩 Pior: `${worst_trade:+,.2f}`")

        if regime_changes > 0:
            lines.append(f"🔄 Mudanças de regime: `{regime_changes}`")

        message = "\n".join(lines)
        return self._send_message(message)

    def send_error(
        self,
        error_message: str,
        error_type: str = "Error",
        context: str = None
    ) -> bool:
        """
        Envia alerta de erro.

        Sempre envia, mesmo em horário silencioso.
        """
        lines = [
            f"🚨 *{error_type}*",
            "",
            f"`{error_message}`",
        ]

        if context:
            lines.append("")
            lines.append(f"📍 Contexto: {context}")

        lines.append("")
        lines.append(f"_Horário: {datetime.now().strftime('%d/%m %H:%M:%S')}_")

        message = "\n".join(lines)
        return self._send_message(message, disable_notification=False)

    def send_startup(self, mode: str = "paper", version: str = "1.0") -> bool:
        """Envia notificação de inicialização do bot."""
        lines = [
            "🤖 *Bot Iniciado*",
            "",
            f"📌 Modo: `{mode}`",
            f"📦 Versão: `{version}`",
            f"⏰ Horário: `{datetime.now().strftime('%d/%m/%Y %H:%M')}`",
            "",
            "Aguardando sinais de mercado..."
        ]

        message = "\n".join(lines)
        return self._send_message(message)

    def send_shutdown(self, reason: str = "Manual") -> bool:
        """Envia notificação de desligamento do bot."""
        lines = [
            "🔴 *Bot Encerrado*",
            "",
            f"📍 Motivo: `{reason}`",
            f"⏰ Horário: `{datetime.now().strftime('%d/%m/%Y %H:%M')}`",
        ]

        message = "\n".join(lines)
        return self._send_message(message)

    def send_trade_closed(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        duration: str = None
    ) -> bool:
        """Envia notificação de trade fechado."""
        # Emoji baseado no resultado
        if pnl > 0:
            result_emoji = "💰"
            result_text = "LUCRO"
        else:
            result_emoji = "📉"
            result_text = "PERDA"

        lines = [
            f"{result_emoji} *Trade Fechado* - {symbol}",
            "",
            f"📊 Lado: `{side}`",
            f"➡️ Entrada: `${entry_price:,.2f}`",
            f"⬅️ Saída: `${exit_price:,.2f}`",
            "",
            f"💵 {result_text}: `${pnl:+,.2f}` ({pnl_pct:+.1f}%)",
        ]

        if duration:
            lines.append(f"⏱️ Duração: `{duration}`")

        message = "\n".join(lines)
        return self._send_message(message)

    def send_circuit_breaker(
        self,
        reason: str,
        details: Dict[str, Any] = None
    ) -> bool:
        """Envia alerta de circuit breaker ativado."""
        lines = [
            "⚠️ *Circuit Breaker Ativado*",
            "",
            f"🚫 Motivo: `{reason}`",
        ]

        if details:
            lines.append("")
            for key, value in details.items():
                lines.append(f"• {key}: `{value}`")

        lines.append("")
        lines.append("_Trading pausado temporariamente_")

        message = "\n".join(lines)
        return self._send_message(message, disable_notification=False)


# Singleton global
_notifier: Optional[TelegramNotifier] = None


def get_notifier() -> TelegramNotifier:
    """Obtém instância global do notifier."""
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier


def notify_trade(symbol: str, action: str, **kwargs) -> bool:
    """Atalho para notificação de trade."""
    return get_notifier().send_trade_signal(symbol=symbol, action=action, **kwargs)


def notify_error(message: str, **kwargs) -> bool:
    """Atalho para notificação de erro."""
    return get_notifier().send_error(error_message=message, **kwargs)


def notify_status(**kwargs) -> bool:
    """Atalho para notificação de status."""
    return get_notifier().send_status(**kwargs)
