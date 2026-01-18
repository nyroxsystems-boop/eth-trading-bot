import { useState, useEffect } from 'react'
import { Sun, Moon, Monitor } from 'lucide-react'

type Theme = 'light' | 'dark' | 'system'

const ThemeToggle = () => {
    const [theme, setTheme] = useState<Theme>(() => {
        // Check localStorage first
        const saved = localStorage.getItem('theme') as Theme
        if (saved) return saved
        return 'system'
    })

    useEffect(() => {
        const root = document.documentElement

        if (theme === 'system') {
            // Remove data-theme to use CSS media query
            root.removeAttribute('data-theme')
            localStorage.removeItem('theme')
        } else {
            root.setAttribute('data-theme', theme)
            localStorage.setItem('theme', theme)
        }
    }, [theme])

    const cycleTheme = () => {
        const themes: Theme[] = ['dark', 'light', 'system']
        const currentIndex = themes.indexOf(theme)
        const nextIndex = (currentIndex + 1) % themes.length
        setTheme(themes[nextIndex])
    }

    const getIcon = () => {
        switch (theme) {
            case 'light':
                return <Sun size={18} />
            case 'dark':
                return <Moon size={18} />
            case 'system':
                return <Monitor size={18} />
        }
    }

    const getLabel = () => {
        switch (theme) {
            case 'light':
                return 'Light'
            case 'dark':
                return 'Dark'
            case 'system':
                return 'Auto'
        }
    }

    return (
        <button
            onClick={cycleTheme}
            title={`Theme: ${getLabel()}`}
            style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 12px',
                background: 'var(--glass-bg)',
                border: '1px solid var(--glass-border)',
                borderRadius: '8px',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                fontSize: '13px',
                fontWeight: 500
            }}
            onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--primary-purple)'
                e.currentTarget.style.color = 'var(--text-primary)'
            }}
            onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--glass-border)'
                e.currentTarget.style.color = 'var(--text-secondary)'
            }}
        >
            {getIcon()}
            <span style={{
                fontSize: '12px',
                minWidth: '32px'
            }}>
                {getLabel()}
            </span>
        </button>
    )
}

export default ThemeToggle
