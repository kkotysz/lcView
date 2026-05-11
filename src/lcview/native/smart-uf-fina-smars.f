      program prog
      implicit double precision (a-h,o-z)
      character *1 h
      character *16 ccc
      parameter (NN = 100000)
      dimension nt(NN,1000),freqb(1000)
      dimension ids(NN),dif(NN)
      data stonthe,snt2,frd /3.d0,3.4d0,50.d0/

      narg = command_argument_count()
      if (narg.ne.5) then
        write (*,'('' Wrong number of arguments:'',i5)') narg
        write (*,'('' Usage: smart-uf-final <T> <nh> '',
     *        ''<n2> <n3> <n4>'')')
        stop
      end if

      call get_command_argument(1,ccc)
      read (ccc,*) tran
      resol = 0.5d0/tran
      call get_command_argument(2,ccc)
      read (ccc,*) nmax1
      if (nmax1.lt.2) nmax1 = 2
      call get_command_argument(3,ccc)
      read (ccc,*) nmax2
      call get_command_argument(4,ccc)
      read (ccc,*) nmax3
      call get_command_argument(5,ccc)
      read (ccc,*) nmax4

      do i = 1,NN
         dif(i) = 0.d0
      end do


C  Czytamy starego freq-a...

      open (1, file = 'freq')
      read (1,*) nb,nall
      write (*,'('' NORIG, NALL: '',2i7)') nb,nall
      norig = nall
      do i = 1,nb
         read (1,*) freqb(i)
      end do
      do i = 1,nall
         read (1,*) (nt(i,j), j = 1,nb)
      end do
      close(1)

C Czytamy 'hars-ite.err' i konczymy, jesli sie nie zbiega

      open (4, file = 'hars-ite.err')
      read (4,*) idd
      close(4)
      if (idd.ne.0) then
          h = '*'
c          goto 88
      end if

C  Czytamy resid.max

      open (1, file = 'resid.m')
      read (1,*) nf,f,p,a,ston
      write (*,'('' Frequency: '',f12.6)') f
c   44 freq = f
      freq = f
c    4 continue
      close(1)

      idx = 0

C  Harmonika ?

      do i = 1,nb
         do j = 2,nmax1
            harm = freqb(i)*dble(j)
            if ((dabs(harm-freq).lt.resol).and.
     *        (freqb(i).gt.resol)) then
                nall = nall + 1
                do k = 1,nb
                   nt(nall,k) = 0
                end do
                dif(nall) = harm - freq
                ids(nall) = 1
                nt(nall,i) = j
                h = 'H'
c                write (*,'('' Harmonic '',i4,'' of #'',i3,f12.6)')
c     *              j,i,freqb(i)
c                goto 99
            end if
c            if ((dabs(harmm-freq).lt.resol).and.
c     *        (freqb(i).gt.resol)) then
c                nall = nall + 1
c                do k = 1,nb
c                   nt(nall,k) = 0
c                end do
c                nt(nall,i) = j
c                h = 'H'
c                write (*,'('' Mir.harmonic '',i4,'' of #'',i3,f12.6)')
c     *              j,i,freqb(i)
c                goto 99
c            end if

         end do
      end do



C Subharmonika?

      do i = 1,nb
         harm = freqb(i)/2.d0
         if ((dabs(harm-freq).lt.resol).and.(harm.gt.resol)) then
            write (*,'('' SUBHARMONIC OF FREQ. :'',i5,f12.6)') i,
     *         freqb(i)
c             nb = 1
c             nall = 2
c             freqb(1) = freqb(i)/2.d0
c             nt(1,1) = 1
c             nt(2,1) = 2
c                dif(nall) = harm - freq
c                ids(nall) = 1
c             h = 'S'
c                write (*,'('' Subharmonic of #'',i3,f12.6)')
c     *              i,freqb(i)
c             goto 99
         end if
c         if ((dabs(harmm-freq).lt.resol).and.(harm.gt.resol)) then
c             nb = 1
c             nall = 2
c            freqb(1) = freqb(i)/2.d0
c             nt(1,1) = 1
c             nt(2,1) = 2
c             h = 'S'
c                write (*,'('' Mirror subharmonic of #'',i3,f12.6)')
c     *              i,freqb(i)
c             goto 99
c         end if
      end do


C   Czestosci kombinacyjne

C WSZYSTKIE STOPNIA CO NAJWYZEJ 4, PODWOJNE

      if (nb.lt.2) goto 23
      do i = 1,nb
        do j = i+1,nb
          do n1 = -nmax2,nmax2
          do n2 = -nmax2,nmax2
c            if ((abs(n1)+abs(n2)).gt.4) goto 22
            if ((n1.eq.0).or.(n2.eq.0)) goto 22
            harm = dble(n1)*freqb(i) + dble(n2)*freqb(j)
            if (harm.lt.0.d0) goto 22
            if ((dabs(harm-freq).lt.resol).and.
     *           (harm.gt.resol).and.(freqb(i).gt.resol).and.
     *           (freqb(j).gt.resol)) then
                nall = nall + 1
                do k = 1,nb
                   nt(nall,k) = 0
                end do
                dif(nall) = harm - freq
                ids(nall) = 2
                nt(nall,i) = n1
                nt(nall,j) = n2
                h = 'C'
c                write (*,'('' Combination frequency 2.'')')
c                write (*,'(2i6,f12.6)') n1,i,freqb(i)
c                write (*,'(2i6,f12.6)') n2,j,freqb(j)
c                goto 99
            end if
   22       continue
          end do
          end do
        end do
      end do
c      do i = 1,nb
c        do j = i+1,nb
c          do n1 = -15,15
c          do n2 = -15,15
cc            if ((abs(n1)+abs(n2)).gt.4) goto 29
c            if ((n1.eq.0).or.(n2.eq.0)) goto 29
c            harm = dble(n1)*freqb(i) + dble(n2)*freqb(j)
c            harmm = 2.d0*mirfr - harm
c            if (harmm.lt.0.d0) goto 29
cc            write (*,'(4i5,3f10.4)') i,j,n1,n2,harm,harmm,harmm-freq
c            if ((dabs(harmm-freq).lt.resol).and.
c     *           (harmm.gt.resol).and.(freqb(i).gt.resol).and.
c     *           (freqb(j).gt.resol)) then
c                nall = nall + 1
c                do k = 1,nb
c                   nt(nall,k) = 0
c                end do
c                nt(nall,i) = n1
c                nt(nall,j) = n2
c                h = 'C'
c                write (*,'('' Mir.combination frequency 2.'')')
c                write (*,'(2i6,f12.6)') n1,i,freqb(i)
c                write (*,'(2i6,f12.6)') n2,j,freqb(j)
cc                goto 99
c            end if
c   29       continue
c          end do
c          end do
c        end do
c      end do

   23    continue



C WSZYSTKIE STOPNIA CO NAJWYZEJ 4, POTRÓJNE
      if (nb.lt.3) goto 25
      do i = 1,nb
         do j = i+1,nb
            do k = j+1,nb
          do n1 = -nmax3,nmax3
          do n2 = -nmax3,nmax3
          do n3 = -nmax3,nmax3
c            if ((abs(n1)+abs(n2)+abs(n3)).gt.4) goto 24
            if ((n1.eq.0).or.(n2.eq.0).or.(n3.eq.0)) goto 24
            harm = dble(n1)*freqb(i) + dble(n2)*freqb(j) +
     *             dble(n3)*freqb(k)
            if (harm.lt.0.d0) goto 24
            if ((dabs(harm-freq).lt.resol).and.
     *           (harm.gt.resol).and.(freqb(i).gt.resol).and.
     *           (freqb(j).gt.resol).and.(freqb(k).gt.resol)) then
                nall = nall + 1
                do kk = 1,nb
                   nt(nall,kk) = 0
                end do
                dif(nall) = harm - freq
                ids(nall) = 3
                nt(nall,i) = n1
                nt(nall,j) = n2
                nt(nall,k) = n3
                h = 'C'
c                write (*,'('' Combination frequency 3.'')')
c                write (*,'(2i6,f12.6)') n1,i,freqb(i)
c                write (*,'(2i6,f12.6)') n2,j,freqb(j)
cc               write (*,'(2i6,f12.6)') n3,k,freqb(k)
c                goto 99
            end if
   24       continue
          end do
          end do
          end do
         end do
         end do
       end do

c      do i = 1,nb
c         do j = i+1,nb
c            do k = j+1,nb
c          do n1 = -4,4
c          do n2 = -4,4
c          do n3 = -4,4
cc            if ((abs(n1)+abs(n2)+abs(n3)).gt.4) goto 30
c            if ((n1.eq.0).or.(n2.eq.0).or.(n3.eq.0)) goto 30
c            harmm = 2.d0*mirfr - (dble(n1)*freqb(i) + dble(n2)*freqb(j)+
c     *             dble(n3)*freqb(k))
c            if (harmm.lt.0.d0) goto 30
c            if ((dabs(harmm-freq).lt.resol).and.
c     *           (harmm.gt.resol).and.(freqb(i).gt.resol).and.
c     *           (freqb(j).gt.resol).and.(freqb(k).gt.resol)) then
c                nall = nall + 1
c                do kk = 1,nb
c                   nt(nall,kk) = 0
c                end do
c                nt(nall,i) = n1
c                nt(nall,j) = n2
c                nt(nall,k) = n3
c                h = 'C'
c                write (*,'('' Mir.combination frequency 3.'')')
c                write (*,'(2i6,f12.6)') n1,i,freqb(i)
c                write (*,'(2i6,f12.6)') n2,j,freqb(j)
c                write (*,'(2i6,f12.6)') n3,k,freqb(k)
cc                goto 99
c            end if
c   30       continue
c          end do
c          end do
c          end do
c         end do
c         end do
c       end do


   25  continue


C WSZYSTKIE STOPNIA CO NAJWYZEJ 4, POCZWÓRNE
      if (nb.lt.4) goto 27
      do i = 1,nb
         do j = i+1,nb
            do k = j+1,nb
              do l = k+1,nb
          do n1 = -nmax4,nmax4
          do n2 = -nmax4,nmax4
          do n3 = -nmax4,nmax4
          do n4 = -nmax4,nmax4
c            if ((abs(n1)+abs(n2)+abs(n3)+abs(n4)).gt.4) goto 26
            if ((n1.eq.0).or.(n2.eq.0).or.(n3.eq.0).or.(n4.eq.0))
     *          goto 26
            harm = dble(n1)*freqb(i) + dble(n2)*freqb(j) +
     *             dble(n3)*freqb(k) + dble(n4)*freqb(l)
            if (harm.lt.0.d0) goto 26
            if ((dabs(harm-freq).lt.resol).and.
     *           (harm.gt.resol).and.(freqb(i).gt.resol).and.
     *           (freqb(j).gt.resol).and.(freqb(k).gt.resol).and.
     *           (freqb(l).gt.resol)) then
                nall = nall + 1
                do kk = 1,nb
                   nt(nall,kk) = 0
                end do
                dif(nall) = harm - freq
                ids(nall) = 4
                nt(nall,i) = n1
                nt(nall,j) = n2
                nt(nall,k) = n3
                nt(nall,l) = n4
                h = 'C'
c                write (*,'('' Combination frequency 4.'')')
c                write (*,'(2i6,f12.6)') n1,i,freqb(i)
c                write (*,'(2i6,f12.6)') n2,j,freqb(j)
c                write (*,'(2i6,f12.6)') n3,k,freqb(k)
c                write (*,'(2i6,f12.6)') n4,l,freqb(l)
c                goto 99
            end if
   26       continue
          end do
          end do
          end do
          end do
         end do
         end do
         end do
       end do
c      do i = 1,nb
c         do j = i+1,nb
c            do k = j+1,nb
c              do l = k+1,nb
c          do n1 = -2,2
c          do n2 = -2,2
c          do n3 = -2,2
c          do n4 = -2,2
cc            if ((abs(n1)+abs(n2)+abs(n3)+abs(n4)).gt.4) goto 31
c            if ((n1.eq.0).or.(n2.eq.0).or.(n3.eq.0).or.(n4.eq.0))
c     *          goto 31
c            harmm = 2.d0*mirfr - (dble(n1)*freqb(i) + dble(n2)*freqb(j)+
c     *             dble(n3)*freqb(k) + dble(n4)*freqb(l))
c            if (harmm.lt.0.d0) goto 31
c            if ((dabs(harm-freq).lt.resol).and.
c     *           (harmm.gt.resol).and.(freqb(i).gt.resol).and.
c     *           (freqb(j).gt.resol).and.(freqb(k).gt.resol).and.
c     *           (freqb(l).gt.resol)) then
c                nall = nall + 1
c                do kk = 1,nb
c                   nt(nall,kk) = 0
c                end do
c                nt(nall,i) = n1
c                nt(nall,j) = n2
c                nt(nall,k) = n3
c                nt(nall,l) = n4
c                h = 'C'
c                write (*,'('' Mir.combination frequency 4.'')')
c                write (*,'(2i6,f12.6)') n1,i,freqb(i)
c                write (*,'(2i6,f12.6)') n2,j,freqb(j)
c                write (*,'(2i6,f12.6)') n3,k,freqb(k)
c                write (*,'(2i6,f12.6)') n4,l,freqb(l)
cc                goto 99
c            end if
c   31       continue
c          end do
c          end do
c          end do
c          end do
c         end do
c         end do
c         end do
c       end do
   27  continue




C WSZYSTKIE STOPNIA CO NAJWYZEJ 2, POPIATNE
c      if (nb.lt.5) goto 37
c      do i = 1,nb
c         do j = i+1,nb
c            do k = j+1,nb
c              do l = k+1,nb
c                 do m = l+1,nb
c          do n1 = -nmax5,nmax5
c          do n2 = -nmax5,nmax5
c          do n3 = -nmax5,nmax5
c          do n4 = -nmax5,nmax5
c          do n5 = -nmax5,nmax5
cc            if ((abs(n1)+abs(n2)+abs(n3)+abs(n4)).gt.4) goto 26
c            if ((n1.eq.0).or.(n2.eq.0).or.(n3.eq.0).or.(n4.eq.0)
c     *          .or.(n5.eq.0)) goto 36
c            harm = dble(n1)*freqb(i) + dble(n2)*freqb(j) +
c     *             dble(n3)*freqb(k) + dble(n4)*freqb(l) +
c     *             dble(n5)*freqb(m)
c            if (harm.lt.0.d0) goto 36
c            if ((dabs(harm-freq).lt.resol).and.
c     *           (harm.gt.resol).and.(freqb(i).gt.resol).and.
c     *           (freqb(j).gt.resol).and.(freqb(k).gt.resol).and.
c     *           (freqb(l).gt.resol).and.(freqb(m).gt.resol)) then
c                nall = nall + 1
c                do kk = 1,nb
c                   nt(nall,kk) = 0
c                end do
c                dif(nall) = harm - freq
c                ids(nall) = 5
c                nt(nall,i) = n1
c                nt(nall,j) = n2
c                nt(nall,k) = n3
c                nt(nall,l) = n4
c                nt(nall,m) = n5
c                h = 'C'
c                write (*,'('' Combination frequency 5.'')')
c                write (*,'(2i6,f12.6)') n1,i,freqb(i)
c                write (*,'(2i6,f12.6)') n2,j,freqb(j)
c                write (*,'(2i6,f12.6)') n3,k,freqb(k)
c                write (*,'(2i6,f12.6)') n4,l,freqb(l)
c                write (*,'(2i6,f12.6)') n5,m,freqb(m)
c                goto 99
c            end if
c   36       continue
c          end do
c          end do
c          end do
c          end do
c          end do
c         end do
c         end do
c         end do
c         end do
c       end do
c   37  continue


C  Harmonika zwierciadlana ?

c      do i = 1,nb
c         do j = 2,200
c            dmir = 2.d0*mirfr - freq
c            freqt = freq + 2.d0*dmir
c            harm = freqb(i)*dble(j)
c            if ((dabs(harm-freqt).lt.resol).and.
c     *        (freqb(i).gt.resol)) then
c                nall = nall + 1
c                do k = 1,nb
c                   nt(nall,k) = 0
c                end do
c                nt(nall,i) = j
c                h = 'H'
c                write (*,'('' Mir.Harmonic '',i4,'' of #'',i3,f12.6)')
c     *              j,i,freqb(i)
c                goto 99
c            end if
c         end do
c      end do

C   Nowa czestosc bazowa

      nb = nb + 1
      nall = nall + 1
      freqb(nb) = freq
      do i = 1,nb
         nt(nall,i) = 0
      end do
      nt(nall,nb) = 1
      h = 'B'
c      write (*,'('' New basic frequency.'')')

c   99 continue

c      if (nall.eq.1) goto 100
c      do i = 1,nall-1
c         do j = i+1,nall
c            nsame = 0
c            do k = 1,nb
c               if (nt(i,k).eq.nt(j,k)) nsame = nsame + 1
c            end do
c            if (nsame.eq.nb) then
c               h = '!'
c                 write (*,'('' An unresolved peak detected !!! '')')
c               goto 88
c            end if
c         end do
c      end do

c  100 continue
c      if (f(1).lt.frd) then
c        stt = stonthe
c      else
c        stt = snt2
c      end if

c      if (ston(1).gt.stt) then
c         open (5, file = 'test.op')
c         write (5,'('' Freq. updated'')')
c         close(5)
c      else
c         open (1, file = 'history',access='append')
c         h = '-'
c         write (1,'(a1,f11.6,f7.2)') h,freq,ston(1)
c         close(1)
c         goto 999
c      end if


C  Zapisujemy nowego

c      open (1, file = 'freq.new')
      open (2, file = 'freq.poss')
c      write (1,'(2i7)') nb,nall
c      do i = 1,nb
c         write (1,'(f12.6)') freqb(i)
c      end do
      do i = 1,nall
         nd1 = 0
         nd2 = 0
         do j = 1,nb
            nd1 = nd1 + abs(nt(i,j))
            nd2 = nd2 + abs(nt(i,j))*j
         end do
         sdif = dble(nd2)/dexp(-100.d0*dabs(dif(i)))/10.d0
c         write (1,'(999i4)') (nt(i,j), j = 1,nb)
         if (i.gt.norig) then
           if(ids(i).lt.2)
     *     write (2,'(f7.2,i7,2i5,f8.4,999i4)') sdif,ids(i),nd1,nd2,
     *       dif(i),(nt(i,j), j = 1,nb)
           if(ids(i).eq.2)
     *     write (2,'(f7.2,i6,1x,2i5,f8.4,999i4)') sdif,ids(i),nd1,nd2,
     *       dif(i),(nt(i,j), j = 1,nb)
           if(ids(i).eq.3)
     *     write (2,'(f7.2,i5,2x,2i5,f8.4,999i4)') sdif,ids(i),nd1,nd2,
     *       dif(i),(nt(i,j), j = 1,nb)
           if(ids(i).eq.4)
     *     write (2,'(f7.2,i4,3x,2i5,f8.4,999i4)') sdif,ids(i),nd1,nd2,
     *       dif(i),(nt(i,j), j = 1,nb)
           if(ids(i).eq.5)
     *     write (2,'(f7.2,i3,4x,2i5,f8.4,999i4)') sdif,ids(i),nd1,nd2,
     *       dif(i),(nt(i,j), j = 1,nb)
         end if
      end do
      write (*,'('' NALL: '',i7)') nall
c      close(1)

c   88 continue
c      open (1, file = 'history',access='append')
c      write (1,'(a1,f11.6,f7.2)') h,freq,ston
c      close(1)
c      if (h.eq.'S') then
c         open (1, file = 'history')
c         read (1,'(a1,f11.6,f7.2)') ah,afreq,aston
c         close(1)
c         open (1, file = 'history')
c         write (1,'(a1,f11.6,f7.2)') ah,afreq,aston
c         write (1,'(a1,f11.6,f7.2)') h,freq,ston
c      end if

c  999 stop
      stop
      end
