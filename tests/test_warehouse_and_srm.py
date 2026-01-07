import duckdb
import numpy as np
from scipy import stats


def test_dq_checks_pass():
    con = duckdb.connect("data/launchlens.duckdb")
    dq = con.execute("SELECT pass FROM dq_checks").fetchall()
    con.close()
    assert len(dq) > 0
    assert all(bool(x[0]) for x in dq)


def test_user_level_srm_ok():
    con = duckdb.connect("data/launchlens.duckdb")
    df = con.execute(
        """
        SELECT variant, COUNT(*) AS n_users
        FROM users
        WHERE experiment_id='exp_checkout_v1'
        GROUP BY 1
        """
    ).fetchdf()
    con.close()

    nc = int(df[df["variant"] == "control"]["n_users"].iloc[0])
    nt = int(df[df["variant"] == "treatment"]["n_users"].iloc[0])

    total = nc + nt
    exp = np.array([total * 0.5, total * 0.5], dtype=float)
    obs = np.array([nc, nt], dtype=float)

    chi2, p = stats.chisquare(f_obs=obs, f_exp=exp)

    # user-level SRM should usually pass
    assert p >= 0.01
