import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button, Chip, Field, Select } from "@blesser/ui";
import * as api from "../lib/api";
import {
  MutationError,
  PageHeader,
  QueryState,
  formatDate,
  useAction,
} from "../components/shared";

export default function Reports() {
  const [filter, setFilter] = useState("open");
  const reports = useQuery({ queryKey: ["reports"], queryFn: api.reports });
  const resolve = useAction(api.resolveReport, "Report resolved");
  const items = (reports.data ?? []).filter(
    (report) => filter === "all" || report.resolved === (filter === "resolved"),
  );
  return (
    <>
      <PageHeader
        title="Reports"
        description="Check problems people have raised and resolve them after reviewing the listing."
      />
      <div className="filters">
        <Field label="Show reports">
          <Select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="open">Unresolved</option>
            <option value="resolved">Resolved</option>
            <option value="all">All reports</option>
          </Select>
        </Field>
      </div>
      <MutationError error={resolve.error} />
      <QueryState query={reports} empty={!items.length}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Reported</th>
                <th>Reason</th>
                <th>Reporter</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((report) => (
                <tr key={report.id}>
                  <td className="nowrap">{formatDate(report.created_at)}</td>
                  <td className="report-reason">{report.reason}</td>
                  <td>{report.email || "Anonymous"}</td>
                  <td>
                    <Chip tone={report.resolved ? "neutral" : "sun"}>
                      {report.resolved ? "Resolved" : "Needs review"}
                    </Chip>
                  </td>
                  <td>
                    <div className="actions">
                      <Link
                        className="text-link underline"
                        to={`/opportunities?id=${encodeURIComponent(report.opportunity_id)}`}
                      >
                        Review listing
                      </Link>
                      {!report.resolved && (
                        <Button
                          size="sm"
                          disabled={resolve.isPending}
                          onClick={() => resolve.mutate(report.id)}
                        >
                          Resolve report
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </QueryState>
    </>
  );
}
