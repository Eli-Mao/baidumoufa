// Standard Windows .NET charting backend; no package install or policy changes.
using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Drawing;
using System.Collections.Generic;
using System.Globalization;
using System.Windows.Forms.DataVisualization.Charting;

public static class RenderV6Charts {
    static double Number(string s) { return double.Parse(s.Replace("%", ""), CultureInfo.InvariantCulture); }
    static string[] SplitCsv(string text) {
        var values = new List<string>(); var cell = new StringBuilder(); bool quoted = false;
        for (int i=0; i<text.Length; i++) {
            char c=text[i];
            if (c=='"') { if (quoted && i+1<text.Length && text[i+1]=='"') {cell.Append('"');i++;} else quoted=!quoted; }
            else if (c==',' && !quoted) {values.Add(cell.ToString());cell.Length=0;} else cell.Append(c);
        }
        values.Add(cell.ToString());return values.ToArray();
    }
    static List<Dictionary<string,string>> Read(string path) {
        var lines=File.ReadAllLines(path,Encoding.UTF8);var head=SplitCsv(lines[0].TrimStart('\uFEFF'));
        var data=new List<Dictionary<string,string>>();
        foreach(var line in lines.Skip(1)) {
            if(String.IsNullOrWhiteSpace(line))continue;
            var cells=SplitCsv(line);var row=new Dictionary<string,string>();
            for(int i=0;i<head.Length;i++)row[head[i]]=cells[i];data.Add(row);
        } return data;
    }
    static Chart Chart(string title,string x,string y) {
        var chart=new Chart {Width=1600,Height=900,BackColor=Color.White,Font=new Font("Segoe UI",14)};
        var area=new ChartArea("Main");area.AxisX.Title=x;area.AxisY.Title=y;
        area.AxisX.TitleFont=new Font("Segoe UI",17);area.AxisY.TitleFont=new Font("Segoe UI",17);
        area.AxisX.LabelStyle.Font=new Font("Segoe UI",14);area.AxisY.LabelStyle.Font=new Font("Segoe UI",14);
        area.AxisX.MajorGrid.Enabled=false;area.AxisY.MajorGrid.LineColor=Color.FromArgb(225,230,235);area.AxisY.Minimum=0;
        chart.ChartAreas.Add(area);
        var legend=new Legend("Legend") {Docking=Docking.Bottom,Alignment=StringAlignment.Center,Font=new Font("Segoe UI",14)};
        chart.Legends.Add(legend);chart.Titles.Add(new Title(title,Docking.Top,new Font("Segoe UI",23,FontStyle.Bold),Color.FromArgb(35,45,55)));
        return chart;
    }
    static Series Add(Chart chart,string name,SeriesChartType type,string color) {
        var s=new Series(name) {ChartType=type,Color=ColorTranslator.FromHtml(color),BorderWidth=3,Font=new Font("Segoe UI",12)};
        chart.Series.Add(s);return s;
    }
    static void Save(Chart chart,string dir,string name) {chart.SaveImage(Path.Combine(dir,name),ChartImageFormat.Png);chart.Dispose();}
    public static void Main(string[] args) {
        string dir=args[0];var trials=Read(Path.Combine(dir,"fair_comparison.csv"));
        string[] algs={"v4","v5","v6"};string[] colors={"#83909C","#DD8E35","#157F93"};
        var chart=Chart("Same V5 warm start: equal-budget refinement", "Optimizer budget (seconds)", "Validated model score");
        chart.ChartAreas[0].AxisX.Minimum=0;chart.ChartAreas[0].AxisX.Maximum=48;chart.ChartAreas[0].AxisX.Interval=12;chart.ChartAreas[0].AxisX.LabelStyle.Format="0";
        chart.ChartAreas[0].AxisY.IsStartedFromZero=false;chart.ChartAreas[0].AxisY.Minimum=30600;
        for(int k=0;k<algs.Length;k++) foreach(int seed in new[]{11,22,33}) {
            var series=Add(chart,algs[k].ToUpper()+" seed "+seed,SeriesChartType.Line,colors[k]);
            series.MarkerStyle=MarkerStyle.Circle;series.MarkerSize=10;
            if(seed==22)series.BorderDashStyle=ChartDashStyle.Dash;if(seed==33)series.BorderDashStyle=ChartDashStyle.Dot;
            foreach(var row in trials.Where(r=>r["algorithm"]==algs[k] && Number(r["seed"])==seed).OrderBy(r=>Number(r["budget_s"])))
                series.Points.AddXY(Number(row["budget_s"]),Number(row["score"]));
        }
        Save(chart,dir,"equal_budget_scores.png");
        var trace=Read(Path.Combine(dir,"best_convergence.csv"));
        chart=Chart("Best enhanced trial: provisional search convergence", "Elapsed optimizer seconds", "Model score (final plan independently accepted)");
        chart.ChartAreas[0].AxisX.Minimum=0;chart.ChartAreas[0].AxisX.Maximum=40;chart.ChartAreas[0].AxisX.Interval=10;chart.ChartAreas[0].AxisX.LabelStyle.Format="0";
        chart.ChartAreas[0].AxisY.IsStartedFromZero=false;chart.ChartAreas[0].AxisY.Minimum=30600;
        var line=Add(chart,"V6",SeriesChartType.StepLine,colors[2]);
        foreach(var row in trace)line.Points.AddXY(Number(row["elapsed_s"]),Number(row["total_score"]));
        Save(chart,dir,"optimization_convergence.png");
        var coverage=Read(Path.Combine(dir,"priority_comparison.csv"));
        chart=Chart("Accepted plan coverage by priority", "Priority", "Unique targets covered (%)");chart.ChartAreas[0].AxisY.Maximum=110;chart.ChartAreas[0].AxisY.Interval=20;
        for(int k=0;k<algs.Length;k++) {
            var series=Add(chart,algs[k].ToUpper(),SeriesChartType.Column,colors[k]);series.IsValueShownAsLabel=true;series.LabelFormat="0.0";
            foreach(var row in coverage)series.Points.AddXY(row["priority"],Number(row[algs[k]+"_rate"])*100);
        }
        Save(chart,dir,"priority_coverage.png");
        var stations=Read(Path.Combine(dir,"station_comparison.csv"));
        chart=Chart("Station resources: V5 and best enhanced plan", "Ground station", "Calendar utilization including switches (%)");chart.ChartAreas[0].AxisX.Interval=1;
        foreach(string alg in new[]{"v5","v6"}) {
            var series=Add(chart,alg.ToUpper(),SeriesChartType.Column,alg=="v5"?colors[1]:colors[2]);
            foreach(var row in stations)series.Points.AddXY(Number(row["station_id"]),Number(row[alg+"_utilization"])*100);
        }
        Save(chart,dir,"station_utilization.png");
        Console.WriteLine("Four charts rendered from recorded CSV results.");
    }
}
