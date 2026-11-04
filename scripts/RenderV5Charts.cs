// Standard Windows .NET charting backend; no package install or policy changes.
using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Drawing;
using System.Collections.Generic;
using System.Globalization;
using System.Windows.Forms.DataVisualization.Charting;

public static class RenderV5Charts {
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
        var chart=Chart("Equal-budget score improvement: three random seeds","Optimizer wall-clock budget (seconds)","Validated score gain over sealed V4 (%)");
        chart.ChartAreas[0].AxisX.Minimum=0;chart.ChartAreas[0].AxisX.Maximum=80;chart.ChartAreas[0].AxisX.Interval=20;
        string[] palette={"#157F93","#DD8E35","#5265A7"};int[] seeds={11,22,33};
        for(int i=0;i<seeds.Length;i++)foreach(string alg in new[]{"v4","v5"}) {
            var s=Add(chart,alg.ToUpper()+" seed "+seeds[i],SeriesChartType.Line,alg=="v4"?"#83909C":palette[i]);
            s.MarkerStyle=MarkerStyle.Circle;s.MarkerSize=12;
            if(alg=="v4") {s.BorderDashStyle=ChartDashStyle.Dash;s.IsVisibleInLegend=i==0;}
            foreach(var row in trials.Where(r=>r["algorithm"]==alg && Number(r["seed"])==seeds[i]).OrderBy(r=>Number(r["budget_s"])))
                s.Points.AddXY(Number(row["budget_s"]),Number(row["gain_pct"]));
        }
        Save(chart,dir,"score_gain_by_budget.png");
        var priorities=Read(Path.Combine(dir,"priority_comparison.csv"));
        chart=Chart("Unique target coverage with unchanged 5 / 3 / 2 weights","Target priority","Unique target coverage (%)");
        chart.ChartAreas[0].AxisY.Maximum=110;chart.ChartAreas[0].AxisY.Interval=20;
        foreach(string alg in new[]{"V4","V5"}) {
            var s=Add(chart,alg,SeriesChartType.Column,alg=="V4"?"#83909C":"#157F93");s.IsValueShownAsLabel=true;s.LabelFormat="0.0";
            string[] names={"High","Medium","Low"};for(int i=0;i<priorities.Count;i++)s.Points.AddXY(names[i],Number(priorities[i][alg+"覆盖率"]));
        }
        Save(chart,dir,"priority_coverage.png");
        var stations=Read(Path.Combine(dir,"station_comparison.csv"));
        chart=Chart("Six-day ground station utilization","Ground station","Calendar utilization including switches (%)");chart.ChartAreas[0].AxisX.Interval=1;
        foreach(string alg in new[]{"V4","V5"}) {
            var s=Add(chart,alg,SeriesChartType.Column,alg=="V4"?"#83909C":"#157F93");
            foreach(var row in stations)s.Points.AddXY(Number(row["station_id"]),100*Number(row[alg=="V4"?"calendar_utilization":"v5_calendar_utilization"]));
        }
        Save(chart,dir,"station_utilization.png");
        Console.WriteLine("Three charts rendered from validated experiment CSV files.");
    }
}
