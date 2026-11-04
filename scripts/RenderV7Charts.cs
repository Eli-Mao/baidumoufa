// Standard Windows .NET charting backend; no package install or policy changes.
using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Drawing;
using System.Collections.Generic;
using System.Globalization;
using System.Windows.Forms.DataVisualization.Charting;

public static class RenderV7Charts {
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
        string dir=args[0];string[] algs={"v6","v7"};string[] colors={"#83909C","#157F93"};
        var trials=Read(Path.Combine(dir,"fair_comparison.csv"));
        var chart=Chart("V6 vs V7: 36 seconds, same accepted V6 start", "Random seed", "Accepted score gain over 31015.978086");
        for(int k=0;k<2;k++) {
            var series=Add(chart,algs[k].ToUpper(),SeriesChartType.Column,colors[k]);series.IsValueShownAsLabel=true;series.LabelFormat="0.0";
            foreach(var row in trials.Where(r=>r["algorithm"]==algs[k]).OrderBy(r=>Number(r["seed"])))
                series.Points.AddXY(row["seed"],Number(row["score"])-31015.978085736664);
        }
        Save(chart,dir,"equal_budget_scores.png");
        var trace=Read(Path.Combine(dir,"best_convergence.csv"));
        chart=Chart("Best V7: provisional move trace; final plan independently accepted", "Search elapsed seconds", "Frozen-model score");
        chart.ChartAreas[0].AxisY.Minimum=31000;chart.ChartAreas[0].AxisY.IsStartedFromZero=false;
        chart.ChartAreas[0].AxisX.Minimum=0;chart.ChartAreas[0].AxisX.Maximum=Math.Ceiling(trace.Max(r=>Number(r["elapsed_s"])));
        chart.ChartAreas[0].AxisX.Interval=20;chart.ChartAreas[0].AxisX.LabelStyle.Format="0";
        var line=Add(chart,"V7",SeriesChartType.StepLine,colors[1]);
        foreach(var row in trace)line.Points.AddXY(Number(row["elapsed_s"]),Number(row["total_score"]));
        Save(chart,dir,"optimization_convergence.png");
        var coverage=Read(Path.Combine(dir,"priority_comparison.csv"));
        chart=Chart("Accepted artifact coverage (search budgets differ)", "Priority", "Unique targets covered (%)");
        chart.ChartAreas[0].AxisY.Maximum=110;chart.ChartAreas[0].AxisY.Interval=20;
        for(int k=0;k<2;k++) {
            var series=Add(chart,algs[k].ToUpper(),SeriesChartType.Column,colors[k]);series.IsValueShownAsLabel=true;series.LabelFormat="0.0";
            foreach(var row in coverage)series.Points.AddXY(row["priority"],Number(row[algs[k]+"_rate"])*100.0);
        }
        Save(chart,dir,"priority_coverage.png");
        Console.WriteLine("Three charts rendered from accepted evidence; no new optimization.");
    }
}
