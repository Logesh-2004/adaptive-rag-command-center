import { AlertCircle, CheckCircle2, Info, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ActivityEvent } from "@/types/api";

const icons = {
  success: CheckCircle2,
  warning: TriangleAlert,
  error: AlertCircle,
  info: Info,
};

export function LogsViewer({ events }: { events: ActivityEvent[] }) {
  return (
    <Card id="logs">
      <CardHeader className="flex flex-row items-center justify-between gap-4 pb-4 space-y-0">
        <div>
          <p className="section-kicker">Session history</p>
          <CardTitle className="mt-1">Recent activity</CardTitle>
        </div>
        <Badge>{events.length} events</Badge>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {events.length ? (
            events.map((event) => {
              const Icon = icons[event.severity];
              return (
                <div key={event.id} className="activity-row depth-card p-4">
                  <div className="flex items-start gap-3">
                    <Icon
                      aria-hidden="true"
                      className={
                        event.severity === "error"
                          ? "mt-0.5 h-4 w-4 text-destructive"
                          : event.severity === "warning"
                            ? "mt-0.5 h-4 w-4 text-warning"
                            : event.severity === "success"
                              ? "mt-0.5 h-4 w-4 text-success"
                              : "mt-0.5 h-4 w-4 text-accent"
                      }
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-sm font-medium">{event.title}</h3>
                          <Badge className="capitalize">{event.type}</Badge>
                        </div>
                        <time className="font-mono text-xs tabular-nums text-muted-foreground">{event.time}</time>
                      </div>
                      <p className="mt-1 break-words text-sm leading-6 text-muted-foreground">{event.detail}</p>
                    </div>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="rounded-lg border border-dashed border-white/15 p-6 text-sm text-muted-foreground">
              Runtime events, warnings, and evaluation outcomes appear here during this dashboard session.
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
