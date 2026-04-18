import { LayoutDashboard, TrendingUp, Settings, Activity } from 'lucide-react'

interface SidebarProps {
  activePage: string
  onNavigate: (page: string) => void
}

const navItems = [
  { id: 'dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { id: 'trading', icon: TrendingUp, label: 'Trading' },
  { id: 'settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar({ activePage, onNavigate }: SidebarProps) {
  return (
    <nav className="sidebar">
      <div className="sidebar-logo">E</div>
      <div className="sidebar-nav">
        {navItems.map(item => (
          <div
            key={item.id}
            className={`nav-item ${activePage === item.id ? 'active' : ''}`}
            onClick={() => onNavigate(item.id)}
          >
            <item.icon size={20} />
            <span className="tooltip">{item.label}</span>
          </div>
        ))}
      </div>
      <div className="nav-item" style={{ marginTop: 'auto' }}>
        <Activity size={18} />
        <span className="tooltip">v3.0</span>
      </div>
    </nav>
  )
}
