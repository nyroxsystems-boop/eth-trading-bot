import { createContext, useContext, useState, ReactNode, useEffect } from 'react'

type Language = 'en' | 'de'

interface Translations {
    [key: string]: {
        en: string
        de: string
    }
}

// Translations dictionary
const translations: Translations = {
    // Navigation
    'nav.dashboard': { en: 'Dashboard', de: 'Dashboard' },
    'nav.trading': { en: 'Trading', de: 'Handel' },
    'nav.analytics': { en: 'Analytics', de: 'Analysen' },
    'nav.social': { en: 'Social', de: 'Sozial' },
    'nav.learning': { en: 'Learning', de: 'Lernen' },
    'nav.portfolio': { en: 'Portfolio', de: 'Portfolio' },
    'nav.journal': { en: 'Journal', de: 'Journal' },
    'nav.earnings': { en: 'Earnings', de: 'Einnahmen' },
    'nav.settings': { en: 'Settings', de: 'Einstellungen' },

    // Common
    'common.save': { en: 'Save', de: 'Speichern' },
    'common.cancel': { en: 'Cancel', de: 'Abbrechen' },
    'common.loading': { en: 'Loading...', de: 'Laden...' },
    'common.error': { en: 'Error', de: 'Fehler' },
    'common.success': { en: 'Success', de: 'Erfolg' },
    'common.active': { en: 'Active', de: 'Aktiv' },
    'common.inactive': { en: 'Inactive', de: 'Inaktiv' },
    'common.export': { en: 'Export', de: 'Exportieren' },
    'common.share': { en: 'Share', de: 'Teilen' },
    'common.refresh': { en: 'Refresh', de: 'Aktualisieren' },

    // Dashboard
    'dashboard.title': { en: 'Dashboard', de: 'Dashboard' },
    'dashboard.welcome': { en: 'Welcome back', de: 'Willkommen zurück' },
    'dashboard.totalPnL': { en: 'Total P&L', de: 'Gesamt P&L' },
    'dashboard.winRate': { en: 'Win Rate', de: 'Gewinnrate' },
    'dashboard.trades': { en: 'Trades', de: 'Trades' },
    'dashboard.todayPnL': { en: "Today's P&L", de: 'Heutiges P&L' },
    'dashboard.balance': { en: 'Balance', de: 'Kontostand' },
    'dashboard.recentTrades': { en: 'Recent Trades', de: 'Letzte Trades' },

    // Trading / Bots
    'trading.bots': { en: 'Bots', de: 'Bots' },
    'trading.strategyLab': { en: 'Strategy Lab', de: 'Strategie-Labor' },
    'trading.botConfig': { en: 'Bot Configuration', de: 'Bot-Konfiguration' },
    'trading.manageBot': { en: 'Manage your trading bot and strategies', de: 'Verwalte deinen Trading-Bot und Strategien' },
    'trading.startBot': { en: 'Start Bot', de: 'Bot starten' },
    'trading.stopBot': { en: 'Stop Bot', de: 'Bot stoppen' },
    'trading.running': { en: 'Running', de: 'Läuft' },
    'trading.stopped': { en: 'Stopped', de: 'Gestoppt' },
    'trading.autoLearning': { en: 'Auto-Learning Active', de: 'Auto-Lernen aktiv' },
    'trading.viewLearning': { en: 'View Learning Progress', de: 'Lernfortschritt anzeigen' },

    // Strategy Lab
    'strategy.templates': { en: 'Templates', de: 'Vorlagen' },
    'strategy.parameters': { en: 'Parameters', de: 'Parameter' },
    'strategy.backtest': { en: 'Backtest', de: 'Backtest' },
    'strategy.builder': { en: 'Builder', de: 'Builder' },
    'strategy.aiSuggestions': { en: 'AI Suggestions', de: 'KI-Vorschläge' },
    'strategy.optimize': { en: 'Optimize', de: 'Optimieren' },
    'strategy.livePreview': { en: 'Live Preview', de: 'Live-Vorschau' },
    'strategy.entryConditions': { en: 'Entry Conditions', de: 'Einstiegsbedingungen' },
    'strategy.exitConditions': { en: 'Exit Conditions', de: 'Ausstiegsbedingungen' },
    'strategy.addCondition': { en: 'Add', de: 'Hinzufügen' },
    'strategy.indicators': { en: 'Indicators', de: 'Indikatoren' },
    'strategy.dragToZones': { en: 'Drag to Entry or Exit zones', de: 'In Einstiegs- oder Ausstiegszonen ziehen' },
    'strategy.runBacktest': { en: 'Run Backtest', de: 'Backtest starten' },
    'strategy.testStrategy': { en: 'Test Strategy', de: 'Strategie testen' },
    'strategy.activate': { en: 'Activate', de: 'Aktivieren' },
    'strategy.applyStrategy': { en: 'Apply Strategy', de: 'Strategie anwenden' },

    // Learning
    'learning.title': { en: 'Auto-Learning Monitor', de: 'Auto-Lern-Monitor' },
    'learning.subtitle': { en: 'Watch your bot learn and improve automatically', de: 'Beobachte wie dein Bot automatisch lernt und sich verbessert' },
    'learning.trainingActive': { en: 'Training Active', de: 'Training aktiv' },
    'learning.trainingPaused': { en: 'Training Paused', de: 'Training pausiert' },
    'learning.overview': { en: 'Overview', de: 'Übersicht' },
    'learning.training': { en: 'Training', de: 'Training' },
    'learning.models': { en: 'Models', de: 'Modelle' },
    'learning.liveLogs': { en: 'Live Logs', de: 'Live-Logs' },
    'learning.totalTested': { en: 'Total Tested', de: 'Gesamt getestet' },
    'learning.bestScore': { en: 'Best Score', de: 'Beste Punktzahl' },
    'learning.applied': { en: 'Applied', de: 'Angewendet' },
    'learning.thisHour': { en: 'This Hour', de: 'Diese Stunde' },
    'learning.learningRate': { en: 'Learning Rate', de: 'Lernrate' },
    'learning.topStrategies': { en: 'Top 10 Strategies', de: 'Top 10 Strategien' },
    'learning.trainingProgress': { en: 'Training Progress', de: 'Trainingsfortschritt' },
    'learning.currentSession': { en: 'Current Training Session', de: 'Aktuelle Trainingssitzung' },
    'learning.hyperparameters': { en: 'Hyperparameters', de: 'Hyperparameter' },
    'learning.rewardHistory': { en: 'Reward History (Last 24h)', de: 'Belohnungsverlauf (Letzte 24h)' },
    'learning.viewDetails': { en: 'View Details', de: 'Details anzeigen' },

    // Analytics
    'analytics.title': { en: 'Analytics', de: 'Analysen' },
    'analytics.performance': { en: 'Performance', de: 'Leistung' },
    'analytics.monthly': { en: 'Monthly', de: 'Monatlich' },
    'analytics.weekly': { en: 'Weekly', de: 'Wöchentlich' },
    'analytics.daily': { en: 'Daily', de: 'Täglich' },

    // Journal
    'journal.title': { en: 'Trading Journal', de: 'Trading-Tagebuch' },
    'journal.subtitle': { en: 'Review your trades and identify patterns', de: 'Überprüfe deine Trades und erkenne Muster' },
    'journal.tradeHistory': { en: 'Trade History', de: 'Trade-Verlauf' },
    'journal.aiInsights': { en: 'AI Insights', de: 'KI-Erkenntnisse' },
    'journal.today': { en: 'Today', de: 'Heute' },
    'journal.last7Days': { en: 'Last 7 Days', de: 'Letzte 7 Tage' },
    'journal.last30Days': { en: 'Last 30 Days', de: 'Letzte 30 Tage' },
    'journal.last90Days': { en: 'Last 90 Days', de: 'Letzte 90 Tage' },
    'journal.avgTrade': { en: 'Avg Trade', de: 'Ø Trade' },
    'journal.totalTrades': { en: 'Total Trades', de: 'Gesamt Trades' },

    // Social / Copy Trading
    'social.copyTrading': { en: 'Copy Trading', de: 'Copy-Trading' },
    'social.leaderboard': { en: 'Leaderboard', de: 'Rangliste' },
    'social.topTraders': { en: 'Top Traders', de: 'Top-Händler' },
    'social.followers': { en: 'Followers', de: 'Follower' },
    'social.copyThisTrader': { en: 'Copy This Trader', de: 'Diesem Händler folgen' },

    // Earnings
    'earnings.title': { en: 'Earnings', de: 'Einnahmen' },
    'earnings.totalEarnings': { en: 'Total Earnings', de: 'Gesamteinnahmen' },
    'earnings.thisMonth': { en: 'This Month', de: 'Diesen Monat' },
    'earnings.pendingPayout': { en: 'Pending Payout', de: 'Ausstehende Auszahlung' },
    'earnings.referralBonus': { en: 'Referral Bonus', de: 'Empfehlungsbonus' },

    // Settings
    'settings.title': { en: 'Settings', de: 'Einstellungen' },
    'settings.general': { en: 'General', de: 'Allgemein' },
    'settings.account': { en: 'Account', de: 'Konto' },
    'settings.notifications': { en: 'Notifications', de: 'Benachrichtigungen' },
    'settings.security': { en: 'Security', de: 'Sicherheit' },
    'settings.language': { en: 'Language', de: 'Sprache' },
    'settings.theme': { en: 'Theme', de: 'Design' },
    'settings.darkMode': { en: 'Dark Mode', de: 'Dunkelmodus' },
    'settings.lightMode': { en: 'Light Mode', de: 'Hellmodus' },

    // Auth
    'auth.login': { en: 'Login', de: 'Anmelden' },
    'auth.register': { en: 'Register', de: 'Registrieren' },
    'auth.logout': { en: 'Logout', de: 'Abmelden' },
    'auth.email': { en: 'Email', de: 'E-Mail' },
    'auth.password': { en: 'Password', de: 'Passwort' },
    'auth.forgotPassword': { en: 'Forgot Password?', de: 'Passwort vergessen?' },

    // Table Headers
    'table.rank': { en: 'Rank', de: 'Rang' },
    'table.score': { en: 'Score', de: 'Punktzahl' },
    'table.winRate': { en: 'Win Rate', de: 'Gewinnrate' },
    'table.roi': { en: 'ROI', de: 'ROI' },
    'table.status': { en: 'Status', de: 'Status' },
    'table.time': { en: 'Time', de: 'Zeit' },
    'table.side': { en: 'Side', de: 'Seite' },
    'table.entry': { en: 'Entry', de: 'Einstieg' },
    'table.exit': { en: 'Exit', de: 'Ausstieg' },
    'table.pnl': { en: 'P&L', de: 'P&L' },
    'table.duration': { en: 'Duration', de: 'Dauer' },
    'table.signals': { en: 'Signals', de: 'Signale' },
}

interface LanguageContextType {
    language: Language
    setLanguage: (lang: Language) => void
    t: (key: string) => string
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

export function LanguageProvider({ children }: { children: ReactNode }) {
    const [language, setLanguageState] = useState<Language>(() => {
        const saved = localStorage.getItem('language')
        return (saved as Language) || 'en'
    })

    const setLanguage = (lang: Language) => {
        setLanguageState(lang)
        localStorage.setItem('language', lang)
    }

    useEffect(() => {
        const saved = localStorage.getItem('language')
        if (saved && (saved === 'en' || saved === 'de')) {
            setLanguageState(saved)
        }
    }, [])

    const t = (key: string): string => {
        const translation = translations[key]
        if (!translation) {
            console.warn(`Translation missing for key: ${key}`)
            return key
        }
        return translation[language]
    }

    return (
        <LanguageContext.Provider value={{ language, setLanguage, t }}>
            {children}
        </LanguageContext.Provider>
    )
}

export function useLanguage() {
    const context = useContext(LanguageContext)
    if (!context) {
        throw new Error('useLanguage must be used within a LanguageProvider')
    }
    return context
}

// Language Switcher Component
export function LanguageSwitcher() {
    const { language, setLanguage } = useLanguage()

    return (
        <div style={{
            display: 'flex',
            gap: '4px',
            padding: '4px',
            background: 'var(--bg-tertiary)',
            borderRadius: '8px'
        }}>
            <button
                onClick={() => setLanguage('en')}
                style={{
                    padding: '6px 12px',
                    background: language === 'en' ? 'var(--glass-bg)' : 'transparent',
                    border: 'none',
                    borderRadius: '6px',
                    color: language === 'en' ? 'var(--text-primary)' : 'var(--text-muted)',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                }}
            >
                🇬🇧 EN
            </button>
            <button
                onClick={() => setLanguage('de')}
                style={{
                    padding: '6px 12px',
                    background: language === 'de' ? 'var(--glass-bg)' : 'transparent',
                    border: 'none',
                    borderRadius: '6px',
                    color: language === 'de' ? 'var(--text-primary)' : 'var(--text-muted)',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                }}
            >
                🇩🇪 DE
            </button>
        </div>
    )
}
