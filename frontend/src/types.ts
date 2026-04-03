export type User = {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: string;
};

export type Citation = {
  source: string;
  excerpt: string;
  page?: string | null;
};

export type ChartPayload = {
  kind: string;
  title: string;
  spec: Record<string, unknown>;
};

export type ChatResponse = {
  conversation_id: number;
  answer: string;
  citations: Citation[];
  chart: ChartPayload | null;
  tool_used: string[];
};

export type ConversationSummary = {
  id: number;
  title: string;
  updated_at: string;
};

export type Message = {
  id?: number;
  role: 'user' | 'assistant';
  content: string;
  citations_json?: string | null;
  chart_json?: string | null;
  created_at?: string;
};
