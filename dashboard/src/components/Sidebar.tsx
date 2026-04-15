import { useState } from 'react'
import { Home, TrendingUp, Bot, Brain, Users, Shield, BarChart3, BookOpen, ChevronDown, ChevronRight, Server, DollarSign, ScrollText, Power, Settings, Database, Crosshair } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useLanguage } from '../contexts/LanguageContext'

interface MenuItem {
    id: string
    icon: React.ElementType
    labelKey: string
    adminOnly?: boolean
}

interface AdminSubItem {
    id: string
    icon: React.ElementType
    label: string
}

interface SidebarProps {
    activePage: string
    onPageChange: (page: string) => void
}

export default function Sidebar({ activePage, onPageChange }: SidebarProps) {
    const { user } = useAuth()
    const { t } = useLanguage()
    const isAdmin = user?.role === 'admin'
    const [adminExpanded, setAdminExpanded] = useState(false)

    // Regular menu items — user-facing only
    const menuItems: MenuItem[] = [
        { id: 'dashboard', icon: Home, labelKey: 'nav.dashboard' },
        { id: 'portfolio', icon: TrendingUp, labelKey: 'nav.portfolio' },
        { id: 'trading', icon: Bot, labelKey: 'nav.trading' },
        { id: 'analytics', icon: BarChart3, labelKey: 'nav.analytics' },
        { id: 'journal', icon: BookOpen, labelKey: 'nav.journal' },
        { id: 'account', icon: Users, labelKey: 'settings.account' },
    ]

    // Admin sub-items
    const adminSubItems: AdminSubItem[] = [
        { id: 'admin', icon: Shield, label: 'Overview' },
        { id: 'admin-users', icon: Users, label: 'Users' },
        { id: 'admin-system', icon: Server, label: 'System' },
        { id: 'admin-bot', icon: Power, label: 'Bot Control' },
        { id: 'admin-logs', icon: ScrollText, label: 'Logs' },
        { id: 'admin-revenue', icon: DollarSign, label: 'Revenue' },
        { id: 'admin-db', icon: Database, label: 'Database' },
        { id: 'settings', icon: Settings, label: 'Settings' },
    ]

    const isAdminPage = activePage.startsWith('admin') || activePage === 'settings'

    return (
        <div className="fixed left-0 top-0 h-screen bg-gradient-to-b from-slate-950 to-slate-900 border-r border-slate-800/50 flex flex-col items-center py-6 z-50 backdrop-blur-xl transition-all duration-300"
            style={{ width: isAdmin && adminExpanded ? '200px' : '80px' }}
        >
            {/* Logo */}
            <div className="mb-8">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/30 hover:shadow-cyan-500/50 transition-all duration-300 hover:scale-110">
                    <span className="text-white font-bold text-xl">E</span>
                </div>
            </div>

            {/* Regular Menu Items */}
            <nav className="flex-1 flex flex-col gap-3 w-full px-4">
                {menuItems.map((item) => {
                    const Icon = item.icon
                    const isActive = item.id === activePage

                    return (
                        <button
                            key={item.id}
                            onClick={() => { onPageChange(item.id); if (adminExpanded) setAdminExpanded(false) }}
                            className={`
                                w-full h-12 rounded-xl flex items-center gap-3
                                transition-all duration-300 relative group
                                ${isActive
                                    ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 shadow-lg shadow-cyan-500/20'
                                    : 'text-slate-400 hover:text-cyan-400 hover:bg-slate-800/50 hover:scale-105'
                                }
                            `}
                            style={{ justifyContent: adminExpanded ? 'flex-start' : 'center', paddingLeft: adminExpanded ? '12px' : '0' }}
                            title={t(item.labelKey)}
                        >
                            <Icon className={`w-5 h-5 flex-shrink-0 transition-transform duration-300 ${isActive ? 'scale-110' : 'group-hover:scale-110'}`} />
                            {adminExpanded && (
                                <span className="text-sm font-medium whitespace-nowrap overflow-hidden">{t(item.labelKey)}</span>
                            )}
                            {!adminExpanded && isActive && (
                                <div className="absolute -right-1 top-1/2 -translate-y-1/2 w-1 h-6 bg-cyan-400 rounded-full shadow-lg shadow-cyan-400/50" />
                            )}
                            {!adminExpanded && (
                                <div className="absolute left-full ml-4 px-3 py-2 bg-slate-800 text-white text-sm rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap shadow-xl border border-slate-700 z-50">
                                    {t(item.labelKey)}
                                </div>
                            )}
                        </button>
                    )
                })}

                {/* Admin Section — only for admins */}
                {isAdmin && (
                    <>
                        {/* Separator */}
                        <div className="my-2 border-t border-yellow-500/20" />

                        {/* Admin Toggle */}
                        <button
                            onClick={() => setAdminExpanded(!adminExpanded)}
                            className={`
                                w-full h-12 rounded-xl flex items-center gap-3
                                transition-all duration-300 relative group
                                ring-1 ring-yellow-500/30
                                ${isAdminPage
                                    ? 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30'
                                    : 'text-yellow-500/70 hover:text-yellow-400 hover:bg-yellow-500/10'
                                }
                            `}
                            style={{ justifyContent: adminExpanded ? 'flex-start' : 'center', paddingLeft: adminExpanded ? '12px' : '0' }}
                            title="Admin Panel"
                        >
                            <Shield className="w-5 h-5 flex-shrink-0" />
                            {adminExpanded && (
                                <>
                                    <span className="text-sm font-bold whitespace-nowrap flex-1 text-left">ADMIN</span>
                                    {adminExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                                </>
                            )}
                            {!adminExpanded && (
                                <div className="absolute left-full ml-4 px-3 py-2 bg-slate-800 text-white text-sm rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap shadow-xl border border-slate-700 z-50">
                                    Admin Panel 👑
                                </div>
                            )}
                        </button>

                        {/* Admin Sub-Items (expanded) */}
                        {adminExpanded && (
                            <div className="flex flex-col gap-1 pl-2 animate-fadeIn">
                                {adminSubItems.map((sub) => {
                                    const SubIcon = sub.icon
                                    const isActive = activePage === sub.id

                                    return (
                                        <button
                                            key={sub.id}
                                            onClick={() => onPageChange(sub.id)}
                                            className={`
                                                w-full h-10 rounded-lg flex items-center gap-3 px-3
                                                transition-all duration-200 text-sm
                                                ${isActive
                                                    ? 'bg-yellow-500/15 text-yellow-300 border border-yellow-500/20'
                                                    : 'text-slate-400 hover:text-yellow-300 hover:bg-slate-800/50'
                                                }
                                            `}
                                        >
                                            <SubIcon className="w-4 h-4 flex-shrink-0" />
                                            <span className="whitespace-nowrap">{sub.label}</span>
                                        </button>
                                    )
                                })}
                            </div>
                        )}
                    </>
                )}
            </nav>

            {/* Bottom indicator */}
            <div className="mt-auto">
                <div className="w-2 h-2 rounded-full bg-green-400 shadow-lg shadow-green-400/50 animate-pulse" title="Live" />
            </div>
        </div>
    )
}
