import { Figure } from "../../components/Figure";
import { StatementCode } from "../../components/StatementCode";
import type { Certificate } from "../../lib/api";

interface ConsensusCertificateProps {
  certificate: Certificate;
}

/**
 * The stamped endorsement block, per section 5.6: the only element in
 * the application permitted the reserved consensus green, and the only
 * one with a 2px border. Everything else stays quiet so this carries
 * the weight.
 */
export function ConsensusCertificate({ certificate }: ConsensusCertificateProps) {
  return (
    <section className="consensus-certificate" aria-labelledby="consensus-certificate-heading">
      <span className="consensus-certificate__stamp">Certified consensus</span>
      <h2 id="consensus-certificate-heading" className="consensus-certificate__heading">
        Consensus certificate
      </h2>
      <StatementCode value={certificate.statement.code} />
      <p className="consensus-certificate__clause" lang={certificate.statement.language}>
        {certificate.statement.text}
      </p>

      <table className="consensus-certificate__table">
        <thead>
          <tr>
            <th scope="col">Faction</th>
            <th scope="col">Participants</th>
            <th scope="col">Agree</th>
          </tr>
        </thead>
        <tbody>
          {certificate.clusters.map((cluster) => (
            <tr key={cluster.cluster}>
              <td>Faction {cluster.cluster + 1}</td>
              <td>
                <Figure value={cluster.participant_count} />
              </td>
              <td>
                <Figure value={`${Math.round(cluster.agree_fraction * 100)}%`} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="consensus-certificate__meta">
        <span>
          <Figure value={certificate.participant_count} /> participants
        </span>
        <span>
          Model run <StatementCode value={`MR-${certificate.model_run_id}`} />
        </span>
      </p>
    </section>
  );
}
