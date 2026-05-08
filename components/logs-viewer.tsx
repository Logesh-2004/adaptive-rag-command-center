import { AlertCircle, CheckCircle2, History, Info, TriangleAlert } from "lucide-react";
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
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <History className="h-4 w-4 text-primary" />
            Logs Viewer
          </CardTitle>
          <Badge>{events.length} recent</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {events.length ? (
            events.map((event) => {
              const Icon = icons[event.severity];
              return (
                <div key={event.id} className="rounded-lg border border-white/10 bg-black/20 p-3">
                  <div className="flex items-start gap-3">
                    <Icon
                      className={
                        event.severity === "error"
                          ? "mt-0.5 h-4 w-4 text-destructive"
                          : event.severity === "warning"
                            ? "mt-0.5 h-4 w-4 text-amber-300"
                            : event.severity === "success"
                              ? "mt-0.5 h-4 w-4 text-primary"
                              : "mt-0.5 h-4 w-4 text-sky-300"
                      }
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <h4 className="text-sm font-medium">{event.title}</h4>
                          <Badge>{event.type}</Badge>
                        </div>
                        <span className="font-mono text-xs text-muted-foreground">{event.time}</span>
                      </div>
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">{event.detail}</p>
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
