import { assessmentDisplayName } from "./displayLabels";

export function StandardRecommendationCards({ recommendations, onChoose, disabled = false }: {
  recommendations: { attack_profile_id: string; priority: number }[];
  onChoose?: (method: string) => void; disabled?: boolean;
}) {
  return <div className="standard-recommendations">{recommendations.map(item => <article key={item.attack_profile_id}>
    <h4>{assessmentDisplayName(item.attack_profile_id)}</h4><dl><div><dt>Advisory priority</dt><dd>{item.priority}<span>/100</span></dd></div></dl>
    {onChoose && <button className="secondary-action" type="button" disabled={disabled} onClick={() => onChoose(item.attack_profile_id)}>Create linked assessment</button>}
  </article>)}</div>;
}
