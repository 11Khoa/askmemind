import {
  BookOpenText, LogOut, MessageSquare, Plus, X,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { Chat, User } from '../../lib/types'

type SidebarProps = {
  user: User | null
  chats: Chat[]
  selectedChatId: string | null
  open: boolean
  onClose: () => void
  onNewChat: () => void
  onSelectChat: (chatId: string) => void
  onLogout: () => void
}

function formatDate(value: string, locale: string) {
  return new Intl.DateTimeFormat(locale, {
    month: 'short',
    day: 'numeric',
  }).format(new Date(value))
}

export function Sidebar({
  user,
  chats,
  selectedChatId,
  open,
  onClose,
  onNewChat,
  onSelectChat,
  onLogout,
}: SidebarProps) {
  const { i18n, t } = useTranslation()

  return (
    <aside className={`sidebar ${open ? 'is-open' : ''}`}>
      <div className="sidebar-head">
        <div className="brand">
          <span className="brand-mark"><BookOpenText size={19} /></span>
          <span>{t('brand.name')}</span>
        </div>
        <button className="icon-button mobile-only" title={t('common.closeNavigation')}
          onClick={onClose}><X size={18} /></button>
      </div>

      <button className="new-chat-button" onClick={onNewChat}>
        <Plus size={17} /> {t('chat.newConversation')}
      </button>

      <nav className="chat-navigation" aria-label={t('chat.conversations')}>
        <p className="nav-label">{t('chat.conversations')}</p>
        {chats.length === 0 ? (
          <div className="nav-empty">
            <MessageSquare size={18} />
            <span>{t('chat.emptyNavigation')}</span>
          </div>
        ) : chats.map((chat) => (
          <button key={chat.id}
            className={`chat-link ${selectedChatId === chat.id ? 'is-active' : ''}`}
            onClick={() => onSelectChat(chat.id)}>
            <MessageSquare size={16} />
            <span>{chat.title || t('chat.untitledConversation')}</span>
            <time>{formatDate(chat.updated_at, i18n.language)}</time>
          </button>
        ))}
      </nav>

      <div className="account">
        <div className="avatar">{user?.email.slice(0, 1).toUpperCase()}</div>
        <div className="account-copy">
          <strong>{user?.email.split('@')[0]}</strong>
          <span>{user?.email}</span>
        </div>
        <button className="icon-button" title={t('chat.signOut')} onClick={onLogout}>
          <LogOut size={17} />
        </button>
      </div>
    </aside>
  )
}