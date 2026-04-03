import type { ConversationSummary, User } from '../types';

type Props = {
  conversations: ConversationSummary[];
  activeConversationId: number | null;
  onSelect: (id: number) => void;
  onNewChat: () => void;
  user: User;
  metrics: {
    recentConversationCount: number;
    assistantMessages: number;
    uploadStatus: string | null;
    toolSummary: string;
  };
};

export function Sidebar({ conversations, activeConversationId, onSelect, onNewChat, user, metrics }: Props) {
  return (
    <aside className="sidebar panel dark-panel">
      <div className="brand-block">
        <div className="brand-mark">AI</div>
        <div>
          <h1>Enterprise Intelligence Copilot</h1>
          <p>Knowledge, SQL, forecasting, and charts in one workspace.</p>
        </div>
      </div>

      <button className="new-chat-button" type="button" onClick={onNewChat}>
        + New chat
      </button>

      <section className="sidebar-section">
        <div className="section-title">
          <h2>Recent chats</h2>
          <span>{metrics.recentConversationCount}</span>
        </div>
        <div className="conversation-list">
          {conversations.length === 0 ? (
            <p className="muted">No conversations yet. Send a question to create one.</p>
          ) : (
            conversations.map((conversation) => (
              <button
                key={conversation.id}
                className={conversation.id === activeConversationId ? 'conversation active' : 'conversation'}
                onClick={() => onSelect(conversation.id)}
              >
                <strong>{conversation.title}</strong>
                <span>{new Date(conversation.updated_at).toLocaleString()}</span>
              </button>
            ))
          )}
        </div>
      </section>

      <section className="sidebar-section analytics-card">
        <div className="section-title">
          <h2>Insights dashboard</h2>
          <span>{user.role}</span>
        </div>
        <div className="metric-row">
          <span>Assistant replies</span>
          <strong>{metrics.assistantMessages}</strong>
        </div>
        <div className="metric-row">
          <span>Session state</span>
          <strong>{metrics.toolSummary}</strong>
        </div>
        <div className="metric-row">
          <span>Upload status</span>
          <strong>{metrics.uploadStatus || 'Idle'}</strong>
        </div>
      </section>
    </aside>
  );
}
