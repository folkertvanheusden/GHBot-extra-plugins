#! /bin/sh

echo 'select strftime("%s", `when`), count(*) from history group by strftime("%Y-%m", `when`) order by `when`;' | sqlite3 history.db | tr '|' ' ' | tail -n +2 > /tmp/history.dat

/usr/bin/gnuplot <<EOF > /home/kiking/www/history.png
set term png size 1920,1080
set autoscale
set title "#knageroe"
set timefmt "%s"
set boxwidth 0.4
set grid
set xdata time
set format x "%y-%m-%d\n%H:%M"
set xlabel ""
set ylabel ""
plot '/tmp/history.dat' using 1:2 with lines title 'lines written'
EOF

rm -f /tmp/history.dat
