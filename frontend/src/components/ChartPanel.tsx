import { useEffect, useRef } from 'react';

type Props = {
  chart: { title: string; spec: Record<string, unknown> } | null;
};

export function ChartPanel({ chart }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!chart || !container) {
      return;
    }

    let disposed = false;

    void import('plotly.js-dist-min').then((module) => {
      if (disposed) {
        return;
      }

      const Plotly = (module as { default?: typeof module }).default ?? module;
      const spec = chart.spec as {
        data?: unknown[];
        layout?: Record<string, unknown>;
        config?: Record<string, unknown>;
      };

      void Plotly.newPlot(container, spec.data ?? [], spec.layout ?? {}, {
        responsive: true,
        displayModeBar: false,
        ...(spec.config ?? {}),
      });
    });

    return () => {
      disposed = true;
      void import('plotly.js-dist-min').then((module) => {
        const Plotly = (module as { default?: typeof module }).default ?? module;
        void Plotly.purge(container);
      });
    };
  }, [chart]);

  if (!chart) {
    return (
      <section className="panel chart-panel empty-state">
        <h3>Insights dashboard</h3>
        <p>Charts will appear here when the copilot returns structured data.</p>
      </section>
    );
  }

  return (
    <section className="panel chart-panel">
      <div className="panel-header">
        <h3>{chart.title}</h3>
        <span>Interactive Plotly view</span>
      </div>
      <div ref={containerRef} className="chart-renderer" aria-label={chart.title} />
    </section>
  );
}
