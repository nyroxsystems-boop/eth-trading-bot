import { Home, TrendingUp, RefreshCw, Bot, Settings } from 'lucide-react'

interface SidebarProps {
    activePage?: string
}

export default function Sidebar({ activePage = 'dashboard' }: SidebarProps) {
    const menuItems = [
        { id: 'dashboard', icon: Home, label: 'Dashboard' },
        { id: 'portfolio', icon: TrendingUp, label: 'Portfolio' },
        { id: 'exchange', icon: RefreshCw, label: 'Exchange' },
        { id: 'bots', icon: Bot, label: 'Bots' },
        { id: 'settings', icon: Settings, label: 'Settings' },
    ]

    return (
        <div className="fixed left-0 top-0 h-screen w-20 bg-slate-950 border-r border-slate-800 flex flex-col items-center py-6 z-50">
            {/* Logo */}
            <div className="mb-8">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center">
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
                            className={`
                w-14 h-14 rounded-xl flex items-center justify-center
                transition-all duration-200
                ${isActive
                                    ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                                    : 'text-slate-400 hover:text-cyan-400 hover:bg-slate-800/50'
                                }
              `}
                            title={item.label}
                        >
                            <Icon className="w-6 h-6" />
                        </button>
                    )
                })}
            </nav>
        </div>
    )
}
