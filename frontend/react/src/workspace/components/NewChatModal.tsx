import { X } from "lucide-react";
import { useState } from "react";

type NewChatModalProps = {
  open: boolean
  onClose: () => void
  onCreate: (title: string | null) => void
}

export function NewChatModal({open, onClose, onCreate}: NewChatModalProps) {
  const [title, setTitle] = useState('')

  if(!open) return null

  function submit() {
    onCreate(title.trim() || null)
    setTitle('')
  }

  function close() {
    setTitle('')
    onClose()
  }

  return (
    <div className="modal-backdrop" onMouseDown={close}>
      <div className="modal" onMouseDown={event => event.stopPropagation()}>
        <div className="modal-head">
          <h2>New conversation</h2>
          <button className="icon-button" onClick={close}>
            <X size={18} />
          </button>
        </div>
        <input
          autoFocus
          value={title}
          onChange={event => setTitle(event.target.value)}
          placeholder="Conversation name"
          onKeyDown={event => {
            if(event.key === 'Enter') submit()
            if(event.key === 'Escape') close()
          }}
         />
         <div className="modal-actions">
          <button className="cancel-button" onClick={close}>Cancel</button>
          <button className="create-button" onClick={submit}>Create</button>
         </div>
      </div>
    </div>
  )
}