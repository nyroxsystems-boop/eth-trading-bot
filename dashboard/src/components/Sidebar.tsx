import { Home, TrendingUp, RefreshCw, Bot, Settings, FlaskConical } from 'lucide-react'

interface SidebarProps {
    activePage: string
    onPageChange: (page: string) => void
}

export default function Sidebar({ activePage, onPageChange }: SidebarProps) {
    const menuItems = [
        { id: 'dashboard', icon: Home, label: 'Dashboard' },
        { id: 'portfolio', icon: TrendingUp, label: 'Portfolio' },
        { id: 'trading', icon: RefreshCw, label: 'Trading' },
        { id: 'bots', icon: Bot, label: 'Bots' },
        { id: 'lab', icon: FlaskConical, label: 'Strategy Lab' },
        { id: 'settings', icon: Settings, label: 'Settings' },
    ]

    return (
        <div className="fixed left-0 top-0 h-screen w-20 bg-gradient-to-b from-slate-950 to-slate-900 border-r border-slate-800/50 flex flex-col items-center py-6 z-50 backdrop-blur-xl">
            {/* Logo */}
            <div className="mb-8">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/30 hover:shadow-cyan-500/50 transition-all duration-300 hover:scale-110">
                    <span className="text-white font-bold text-xl">E</span>
                </div>
            </div>

            {/* Menu Items */}
            <nav className="flex-1 flex flex-col gap-4">
                {menuItems.map((item) => {
                    const Icon = item.icon
                    const isActive = item.id === activePage

                    return (
                        <button
                            key={item.id}
                            onClick={() => onPageChange(item.id)}
                            className={`
                w-14 h-14 rounded-xl flex items-center justify-center
                transition-all duration-300 relative group
                ${isActive
                                    ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 shadow-lg shadow-cyan-500/20'
                                    : 'text-slate-400 hover:text-cyan-400 hover:bg-slate-800/50 hover:scale-110'
                                }
              `}
                            title={item.label}
                        >
                            <Icon className={`w-6 h-6 transition-transform duration-300 ${isActive ? 'scale-110' : 'group-hover:scale-110'}`} />

                            {/* Active indicator */}
                            {isActive && (
                                <div className="absolute -right-1 top-1/2 -translate-y-1/2 w-1 h-8 bg-cyan-400 rounded-full shadow-lg shadow-cyan-400/50" />
                            )}

                            {/* Tooltip */}
                            <div className="absolute left-full ml-4 px-3 py-2 bg-slate-800 text-white text-sm rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap shadow-xl border border-slate-700">
                                {item.label}
                            </div>
                        </button>
                    )
                })}
            </nav>

            {/* Bottom indicator */}
            <div className="mt-auto">
                <div className="w-2 h-2 rounded-full bg-green-400 shadow-lg shadow-green-400/50 animate-pulse" title="Live" />
            </div>
        </div>
    )
}
