import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useUIStore } from '@/stores/uiStore'
import { useTranslation } from 'react-i18next'
import { LayoutDashboard, Network, Cpu, Settings, LogOut, Database, ChevronLeft, ChevronRight } from 'lucide-react'

export default function Layout({ children }: { children: React.ReactNode }) {
  const logout = useAuthStore(s => s.logout)
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useTranslation()
  const { lang, setLang } = useUIStore()
  const [collapsed, setCollapsed] = useState(false)

  const navItems = [
    { to: '/overview', icon: LayoutDashboard, label: t('nav.overview') },
    { to: '/pipelines', icon: Database, label: t('nav.pipelines') },
    { to: '/ontologies', icon: Network, label: t('nav.ontologies') },
    { to: '/models', icon: Cpu, label: t('nav.models') },
    { to: '/settings', icon: Settings, label: t('nav.settings') },
  ]

  return (
    <div className="flex h-screen bg-gray-50">
      <aside className={`bg-white border-r flex flex-col transition-all duration-200 ${collapsed ? 'w-16' : 'w-56'}`}>
        <div className={`p-4 border-b flex items-center ${collapsed ? 'justify-center' : 'justify-between'}`}>
          {!collapsed && <h1 className="font-bold text-lg">OntoPrompt</h1>}
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <Link key={to} to={to}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                ${location.pathname.startsWith(to) ? 'bg-black text-white' : 'hover:bg-gray-100 text-gray-700'}`}
              title={collapsed ? label : undefined}>
              <Icon size={16} className="shrink-0" />
              {!collapsed && <span>{label}</span>}
            </Link>
          ))}
        </nav>
        <button onClick={() => setCollapsed(!collapsed)}
          className="flex items-center justify-center p-2 border-t text-gray-400 hover:text-black">
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
        <button onClick={() => { logout(); navigate('/login') }}
          className={`flex items-center gap-2 p-4 text-sm text-gray-500 hover:text-black border-t ${collapsed ? 'justify-center' : ''}`}>
          <LogOut size={16} /> {!collapsed && t('nav.logout')}
        </button>
      </aside>
      <main className="flex-1 overflow-auto p-6">{children}</main>
    </div>
  )
}
