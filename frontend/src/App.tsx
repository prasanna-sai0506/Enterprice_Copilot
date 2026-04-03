import { useEffect, useMemo, useState, type FormEvent, type ChangeEvent } from 'react';
import { ChartPanel } from './components/ChartPanel';
import { Sidebar } from './components/Sidebar';
import { getConversations, getMe, getMessages, login, sendChat, uploadFile } from './api';
import type { ChartPayload, ConversationSummary, Message, User } from './types';

const demoCredentials = { username: 'analyst', password: 'password123' };

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('Why did sales drop in March and what will next quarter look like?');
  const [chart, setChart] = useState<ChartPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);

  useEffect(() => {
    async function bootstrap() {
      try {
        if (!localStorage.getItem('token')) {
          await login(demoCredentials.username, demoCredentials.password);
        }
        const me = await getMe();
        setUser(me);
        const conversationList = await getConversations();
        setConversations(conversationList);
        if (conversationList[0]) {
          setActiveConversationId(conversationList[0].id);
          setMessages(await getMessages(conversationList[0].id));
        }
      } catch (error) {
        setAuthError(error instanceof Error ? error.message : 'Authentication failed');
      } finally {
        setLoading(false);
      }
    }
    bootstrap();
  }, []);

  const toolSummary = useMemo(() => {
    const latestAssistant = [...messages].reverse().find((message) => message.role === 'assistant');
    if (!latestAssistant?.chart_json) {
      return 'Ready';
    }
    return 'Chart generated';
  }, [messages]);

  const recentConversationCount = conversations.length;
  const assistantMessages = messages.filter((message) => message.role === 'assistant').length;

  async function handleSelectConversation(id: number) {
    setActiveConversationId(id);
    const conversationMessages = await getMessages(id);
    setMessages(conversationMessages);
    const assistantMessage = [...conversationMessages].reverse().find((message) => message.role === 'assistant');
    setChart(assistantMessage?.chart_json ? (JSON.parse(assistantMessage.chart_json) as ChartPayload) : null);
  }

  function handleNewChat() {
    setActiveConversationId(null);
    setMessages([]);
    setChart(null);
    setDraft('');
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft.trim()) return;
    setBusy(true);
    try {
      const response = await sendChat(draft, activeConversationId ?? undefined);
      const nextConversationId = response.conversation_id;
      setActiveConversationId(nextConversationId);
      const updatedConversations = await getConversations();
      setConversations(updatedConversations);
      setMessages(await getMessages(nextConversationId));
      setChart(response.chart);
      setDraft('');
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadStatus(`Uploading ${file.name}...`);
    try {
      const result = await uploadFile(file);
      setUploadStatus(`${result.filename} indexed as ${result.chunks_indexed} chunks.`);
    } catch (error) {
      setUploadStatus(error instanceof Error ? error.message : 'Upload failed');
    } finally {
      event.target.value = '';
    }
  }

  if (loading) {
    return <main className="shell loading">Loading secure workspace...</main>;
  }

  if (authError || !user) {
    return (
      <main className="shell error-state">
        <h1>Workspace unavailable</h1>
        <p>{authError || 'Unable to load user session.'}</p>
      </main>
    );
  }

  return (
    <main className="shell dark-shell">
      <Sidebar
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelect={handleSelectConversation}
        onNewChat={handleNewChat}
        user={user}
        metrics={{
          recentConversationCount,
          assistantMessages,
          uploadStatus,
          toolSummary,
        }}
      />
      <section className="workspace">
        <header className="hero panel dark-panel">
          <div>
            <p className="eyebrow">Enterprise chat workspace</p>
            <h2>Hello, {user.full_name}</h2>
            <p>
              Ask about uploaded files, business metrics, or forecasts. The backend routes each request to the right
              tool and keeps the response grounded.
            </p>
          </div>
          <div className="metric-card">
            <span>Session</span>
            <strong>{user.role}</strong>
            <small>{toolSummary}</small>
          </div>
        </header>

        <div className="content-grid">
          <section className="panel chat-panel dark-panel">
            <div className="panel-header">
              <h3>Chat</h3>
              <span>Streaming-ready backend</span>
            </div>
            <form className="composer" onSubmit={handleSubmit}>
              <textarea value={draft} onChange={(event) => setDraft(event.target.value)} rows={4} placeholder="Ask a business question in plain English" />
              <div className="composer-actions">
                <label className="upload-button">
                  <input type="file" accept=".pdf,.docx,.csv,.txt" onChange={handleUpload} />
                  Upload document
                </label>
                <button type="submit" disabled={busy}>
                  {busy ? 'Working...' : 'Send'}
                </button>
              </div>
            </form>
            {uploadStatus ? <p className="status">{uploadStatus}</p> : null}
            <div className="message-list">
              {messages.map((message) => (
                <article key={`${message.role}-${message.id ?? message.created_at}`} className={message.role === 'user' ? 'message user' : 'message assistant'}>
                  <span>{message.role}</span>
                  <p>{message.content}</p>
                </article>
              ))}
            </div>
          </section>
          <ChartPanel chart={chart} />
        </div>
      </section>
    </main>
  );
}
