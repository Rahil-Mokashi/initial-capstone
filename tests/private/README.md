# Private regression test

`test_figure_checker.py::test_real_figures_match_except_the_listed_oddities` reads
`private_samples/sample_daily_report_figures.md`, which is **gitignored and never committed**. On a machine
without it the test skips.

To use it, put one fenced `json` block in that file in the layout `figure_check.py` documents
(`shifts`, `oil`, `grid`, `bowser`, and a `known_oddities` list of finding keys). The two oddities seen on the
owner's sheet are listed there, not corrected:

- `shift1.transaction_total_vs_grid_total_sale`: the shift 1 total in Transaction Details has three decimals and
  differs from the Total Sale printed in the grid by 0.227.
- `shift1.expenses_total`: the shift 1 expense lines add to 7,453 where the sheet's total reads 7,433
  (possibly a misread digit in the photo).
